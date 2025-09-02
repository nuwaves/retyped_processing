# Search API Documentation

The search functionality provides two main endpoints for searching across podcasts, episodes, and tags. All endpoints are versioned and available under `/api/v1/`.

## Base URL

All API endpoints are prefixed with `/api/v1/`

## Endpoints

### 1. Multi-Type Search - `/api/v1/search/`

This endpoint allows searching across multiple content types with separate results for each type.

**Method:** `GET`

**Authentication:** Required

**Query Parameters:**
- `q` (required): Search query string
- `type` (optional): Content type to search (`podcast`, `episode`, `tag`, `all`). Default: `all`
- `limit` (optional): Maximum results per type (1-50). Default: `10`

**Example Request:**
```
GET /api/v1/search/?q=django&type=all&limit=5
```

**Example Response:**
```json
{
    "query": "django",
    "type": "all",
    "total_results": 8,
    "podcasts": [
        {
            "id": 1,
            "name": "Django Weekly",
            "description": "Weekly Django news and tutorials",
            "url": "https://example.com/django-feed.xml",
            "author": "Django Team",
            "created_at": "2024-01-15T10:30:00Z"
        }
    ],
    "episodes": [
        {
            "id": 15,
            "title": "Introduction to Django Models",
            "description": "Learn Django ORM basics",
            "podcast": {
                "id": 1,
                "name": "Django Weekly"
            },
            "pub_date": "2024-02-01T09:00:00Z"
        }
    ],
    "tags": [
        {
            "id": 3,
            "name": "django",
            "slug": "django",
            "description": "Django web framework content"
        }
    ]
}
```

### 2. Unified Search - `/api/v1/unified-search/`

This endpoint returns a single ranked list of results across all content types.

**Method:** `GET`

**Authentication:** Required

**Query Parameters:**
- `q` (required): Search query string
- `limit` (optional): Maximum total results (1-100). Default: `20`

**Example Request:**
```
GET /api/v1/unified-search/?q=django&limit=10
```

**Example Response:**
```json
{
    "query": "django",
    "total_results": 5,
    "results": [
        {
            "type": "podcast",
            "id": 1,
            "title": "Django Weekly",
            "description": "Weekly Django news and tutorials...",
            "url": "                "url": "/api/v1/podcasts/1/",",
            "score": 10,
            "data": {
                "id": 1,
                "name": "Django Weekly",
                "author": "Django Team"
            }
        },
        {
            "type": "episode",
            "id": 15,
            "title": "Introduction to Django Models",
            "description": "Learn Django ORM basics...",
            "url": "/api/v1/episodes/15/",
            "score": 8,
            "podcast_name": "Django Weekly",
            "data": {
                "id": 15,
                "title": "Introduction to Django Models"
            }
        },
        {
            "type": "tag",
            "id": 3,
            "title": "django",
            "description": "Django web framework content",
            "url": "/api/v1/tags/3/",
            "score": 15,
            "data": {
                "id": 3,
                "name": "django",
                "slug": "django"
            }
        }
    ]
}
```

## Search Behavior

### Podcast Search
Searches across the following fields:
- `name`
- `description`
- `author`
- `itunes_subtitle`
- `itunes_summary`
- `itunes_keywords`

### Episode Search
Searches across the following fields:
- `title`
- `description`
- `subtitle`
- `content_encoded`
- `podcast__name` (podcast name)

### Tag Search
Searches across the following fields:
- `name`
- `description`

### Scoring Algorithm (Unified Search)
The unified search uses a simple scoring algorithm:

**Podcasts:**
- Name match: +10 points
- Description match: +5 points
- Author match: +3 points
- iTunes keywords match: +2 points

**Episodes:**
- Title match: +10 points
- Description match: +5 points
- Podcast name match: +3 points
- Subtitle match: +2 points

**Tags:**
- Exact name match: +20 points
- Partial name match: +15 points
- Description match: +5 points

## Error Responses

### 400 Bad Request
```json
{
    "error": "Search query parameter \"q\" is required"
}
```

### 401 Unauthorized
```json
{
    "detail": "Authentication credentials were not provided."
}
```

## Usage Examples

### Search for Python content
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     "http://localhost:8000/api/v1/search/?q=python&type=all&limit=10"
```

### Search only episodes
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     "http://localhost:8000/api/v1/search/?q=tutorial&type=episode"
```

### Unified search with custom limit
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     "http://localhost:8000/api/v1/unified-search/?q=django&limit=5"
```
