from django.core.mail import send_mail
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from molo.core.models import ArticlePage, Main, SiteLanguage, SectionIndexPage
from molo.core.content_import import api

from wagtail.wagtailcore.models import Site
from wagtail.contrib.settings.context_processors import SettingsProxy

from datetime import datetime
from celery import task


@task(ignore_result=True)
def rotate_content():
    main_lang = SiteLanguage.objects.filter(is_main_language=True).first()
    main = Main.objects.all().first()
    index = SectionIndexPage.objects.live().first()
    site = Site.objects.get(is_default_site=True)
    settings = SettingsProxy(site)
    site_settings = settings['core']['SiteSettings']
    if site_settings.content_rotation and \
            site_settings.content_rotation_time == datetime.now().hour:
        if main and index:
            random_article = ArticlePage.objects.live().filter(
                featured_in_latest=False, languages__language__id=main_lang.id
            ).descendant_of(index).order_by('?').first()
            if random_article:
                random_article.featured_in_latest = True
                random_article.save_revision().publish()

                article = main.latest_articles().last()
                article.featured_in_latest = False
                article.save_revision().publish()


def send_import_email(to_email, context):
    from_email = settings.FROM_EMAIL
    plain_body_template = "email_plain_body.html"
    html_body_template = "email_html_body.html"

    subject = settings.CONTENT_IMPORT_SUBJECT
    plain_body = loader.render_to_string(plain_body_template, context)
    html_body = loader.render_to_string(html_body_template, context)

    email_message = EmailMultiAlternatives(
        subject, plain_body, from_email, [to_email])
    email_message.attach_alternative(html_body, 'text/html')
    email_message.send()


@task(ignore_result=True)
def import_content(data, username, email, host):
    repos = api.get_repos(repo_data)
    repo_data, locales = data['repos'], data['locales']

    try:
        result = api.validate_content(repos, locales)
    except InvalidParametersError as e:
        return invalid_parameters_response(e)

    if result['errors']:
        send_import_email(email, {
            'name': username, 'host': host,
            'type': 'validation_failure',
            'errors': result['errors'],
            'warnings': result['warnings']
        })

    api.import_content(repos, locales)
    send_import_email(email, {'name': username, 'host': host})
