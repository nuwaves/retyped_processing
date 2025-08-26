
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from audio_processing.models import Tag, Podcast, Episode


class Command(BaseCommand):
    help = "Seed database for testing and development."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting database seeding...'))
        
        # Create admin user
        self.create_admin_user()
        
        # Create some sample tags
        self.create_sample_tags()
        
        # Create sample RSS feed and podcasts
        self.create_sample_podcasts()
        
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

    def create_sample_podcasts(self):
        """Create a sample RSS feed with podcast episodes"""
        # Create RSS feed
        podcast, created = Podcast.objects.get_or_create(
            url='https://example.com/tech-talk-rss.xml',
            defaults={
                'name': 'Tech Talk Weekly',
                'description': 'Weekly discussions about technology trends and innovations',
                'is_active': True,
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created podcast: {podcast.name}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Podcast "{podcast.name}" already exists')
            )
        
        # Sample podcast episodes
        sample_episodes = [
            {
                'title': 'The Future of AI in Software Development',
                'raw_audio_url': 'https://example.com/audio/episode-001-ai-development.mp3',
                'transcript': '''
                Welcome to Tech Talk Weekly. I'm your host, Sarah Chen, and today we're diving deep into the rapidly evolving world of artificial intelligence in software development.
                
                Our guest today is Dr. Michael Rodriguez, a leading researcher in AI-assisted programming at MIT. Dr. Rodriguez, thanks for joining us.
                
                Dr. Rodriguez: Thank you for having me, Sarah. It's great to be here.
                
                Sarah: Let's start with the big question - how is AI currently changing the way developers work?
                
                Dr. Rodriguez: Well, Sarah, we're seeing AI tools like GitHub Copilot and ChatGPT fundamentally changing how developers approach problem-solving. Instead of starting from scratch, developers can now have AI generate boilerplate code, suggest optimizations, and even help debug complex issues.
                
                Sarah: That's fascinating. What do you think this means for the future of programming as a profession?
                
                Dr. Rodriguez: I believe AI will augment rather than replace developers. The key skills will shift from writing every line of code to understanding systems, architecture, and being able to effectively communicate with AI tools to achieve desired outcomes.
                
                Sarah: Let's talk about some specific examples. Can you share a case where AI significantly improved development productivity?
                
                Dr. Rodriguez: Absolutely. In our recent study, we found that developers using AI-assisted tools completed certain coding tasks 40% faster while maintaining code quality. The biggest gains were in routine tasks like API integration and test writing.
                
                Sarah: That's impressive. What about the challenges? Are there any downsides to this AI revolution?
                
                Dr. Rodriguez: There are definitely concerns. Over-reliance on AI can lead to developers not fully understanding the code they're implementing. There's also the question of code security and the need to verify AI-generated solutions.
                
                Sarah: Those are important considerations. What advice would you give to developers who want to stay relevant in this AI-powered future?
                
                Dr. Rodriguez: Focus on higher-level thinking skills - system design, problem decomposition, and understanding user needs. Also, learn to work effectively with AI tools rather than seeing them as competition.
                
                Sarah: Excellent advice. Before we wrap up, what's one prediction you have for AI in development over the next five years?
                
                Dr. Rodriguez: I think we'll see AI that can understand and work with entire codebases, not just individual functions. This will enable more sophisticated refactoring and architectural improvements.
                
                Sarah: Fascinating insights. Thank you so much for joining us today, Dr. Rodriguez.
                
                Dr. Rodriguez: My pleasure, Sarah.
                
                Sarah: That's all for today's episode of Tech Talk Weekly. Don't forget to subscribe and leave us a review. Until next time, keep coding!
                ''',
                'summary': 'In this episode, Sarah Chen interviews Dr. Michael Rodriguez from MIT about the impact of AI on software development. They discuss how AI tools are changing developer workflows, the benefits and challenges of AI-assisted programming, and predictions for the future of the profession.',
                'release_date': timezone.now() - timedelta(days=7),
                'tags': ['Technology', 'Interview']
            },
            {
                'title': 'Building Scalable Microservices: Lessons Learned',
                'raw_audio_url': 'https://example.com/audio/episode-002-microservices.mp3',
                'transcript': '''
                Hello and welcome back to Tech Talk Weekly. I'm Sarah Chen, and today we're exploring the world of microservices architecture.
                
                Joining me is Emma Thompson, Senior Architect at CloudScale Solutions, who has been instrumental in migrating several large-scale applications from monoliths to microservices.
                
                Emma: Hi Sarah, thanks for having me on the show.
                
                Sarah: Emma, let's start with the basics. When should a company consider moving from a monolithic architecture to microservices?
                
                Emma: That's a great question. The decision shouldn't be taken lightly. Generally, I recommend considering microservices when your team size exceeds what can effectively work on a single codebase, usually around 8-10 developers, or when different parts of your application have vastly different scaling requirements.
                
                Sarah: What are some of the biggest challenges you've encountered during these migrations?
                
                Emma: Data consistency is probably the biggest one. In a monolith, you have ACID transactions across your entire database. With microservices, you need to embrace eventual consistency and implement patterns like saga orchestration.
                
                Sarah: Can you elaborate on the saga pattern?
                
                Emma: Sure. A saga is a sequence of local transactions where each transaction updates data within a single service. If a transaction fails, the saga executes compensating transactions to undo the changes made by preceding transactions.
                
                Sarah: That sounds complex. How do you handle monitoring and debugging across multiple services?
                
                Emma: Observability becomes crucial. We implement distributed tracing using tools like Jaeger or Zipkin, and we ensure every service emits structured logs with correlation IDs. This allows us to trace a request across multiple services.
                
                Sarah: What about testing strategies for microservices?
                
                Emma: We use a testing pyramid approach. Lots of unit tests, fewer integration tests, and minimal end-to-end tests. Contract testing becomes essential - tools like Pact help ensure services can communicate correctly without needing full integration tests for every interaction.
                
                Sarah: Any advice for teams just starting their microservices journey?
                
                Emma: Start small. Don't try to decompose your entire monolith at once. Identify bounded contexts in your domain and extract services one at a time. Also, invest heavily in your deployment pipeline and monitoring from day one.
                
                Sarah: What's one mistake you see teams making repeatedly?
                
                Emma: Creating too many, too small services. Sometimes called "nano-services." This creates excessive network overhead and operational complexity. Services should align with business capabilities, not just technical boundaries.
                
                Sarah: Great insights, Emma. Thank you for sharing your experience with us.
                
                Emma: Thanks for having me, Sarah.
                
                Sarah: That's a wrap for today's episode. Next week, we'll be discussing the latest trends in cloud-native security. Until then, happy coding!
                ''',
                'summary': 'Sarah Chen talks with Emma Thompson, Senior Architect at CloudScale Solutions, about the challenges and best practices of migrating from monolithic to microservices architecture. They cover topics including when to make the transition, data consistency patterns, monitoring strategies, and common pitfalls to avoid.',
                'release_date': timezone.now() - timedelta(days=14),
                'tags': ['Technology', 'Business', 'Interview']
            }
        ]
        
        created_episodes = 0
        for episode_data in sample_episodes:
            # Check if episode already exists
            if Episode.objects.filter(raw_audio_url=episode_data['raw_audio_url']).exists():
                continue
                
            # Create podcast episode
            episode = Episode.objects.create(
                podcast=podcast,
                title=episode_data['title'],
                raw_audio_url=episode_data['raw_audio_url'],
                transcript=episode_data['transcript'],
                summary=episode_data['summary'],
                release_date=episode_data['release_date']
            )

            # Add tags
            for tag_name in episode_data['tags']:
                tag = Tag.objects.get(name=tag_name)
                episode.tags.add(tag)

            created_episodes += 1
            self.stdout.write(
                self.style.SUCCESS(f'Created episode: {episode.title}')
            )
        
        if created_episodes > 0:
            self.stdout.write(
                self.style.SUCCESS(f'Created {created_episodes} sample episodes')
            )
        else:
            self.stdout.write(
                self.style.WARNING('Sample episodes already exist')
            )
