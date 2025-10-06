
def notify_google_of_new_sitemap():
    import requests
    from django.conf import settings
    from django.contrib.sites.models import Site
    current_site = Site.objects.get_current()
    episodes_sitemap_url = f'https://{current_site.domain}/sitemap-episodes.xml'
    google_ping_url = 'http://www.google.com/ping?sitemap=' + episodes_sitemap_url
    try:
        response = requests.get(google_ping_url)
        if response.status_code == 200:
            print('Successfully notified Google of new episodes sitemap.')
        else:
            print(f'Failed to notify Google. Status code: {response.status_code}')
    except Exception as e:
        print(f'Error notifying Google: {e}')
    podcasts_sitemap_url = f'https://{current_site.domain}/sitemap-podcasts.xml'
    google_ping_url = 'http://www.google.com/ping?sitemap=' + podcasts_sitemap_url
    try:
        response = requests.get(google_ping_url)
        if response.status_code == 200:
            print('Successfully notified Google of new podcasts sitemap.')
        else:
            print(f'Failed to notify Google. Status code: {response.status_code}')
    except Exception as e:
        print(f'Error notifying Google: {e}')