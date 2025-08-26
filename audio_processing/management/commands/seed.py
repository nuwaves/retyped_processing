
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from audio_processing.models import Tag, Podcast


class Command(BaseCommand):
    help = "Seed database for testing and development."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting database seeding...'))
        
        # Create admin user
        self.create_admin_user()
        
        # Create some sample tags
        self.create_sample_tags()
        
        self.stdout.write(self.style.SUCCESS('Database seeding completed!'))

    def create_admin_user(self):
        """Create a default admin user for development"""
        username = 'admin'
        email = 'admin@example.com'
        password = 'admin123'
        
        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(f'Admin user "{username}" already exists')
            )
            return
        
        # Create superuser
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        
        self.stdout.write(
            self.style.SUCCESS(f'Created admin user: {username} / {password}')
        )

    def create_sample_tags(self):
        """Create some sample tags for testing"""
        sample_tags = [
            ('Technology', 'Tech-related content'),
            ('Politics', 'Political discussions and news'),
            ('Business', 'Business and entrepreneurship'),
            ('Science', 'Scientific topics and research'),
            ('Health', 'Health and wellness'),
            ('Education', 'Educational content'),
            ('Entertainment', 'Entertainment and media'),
            ('Sports', 'Sports and athletics'),
            ('News', 'Current events and news'),
            ('Interview', 'Interview format episodes'),
        ]
        
        created_count = 0
        for name, description in sample_tags:
            tag, created = Tag.objects.get_or_create(
                name=name,
                defaults={'description': description}
            )
            if created:
                created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'Created {created_count} new tags')
        )
