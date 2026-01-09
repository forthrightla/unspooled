#!/usr/bin/env python3
"""Export listening history SQLite database to JSON files for the visualizer.

Usage:
    python export_data.py /path/to/full_database.db /path/to/output_dir

Output structure (matches visualizer expectations):
    /output_dir
        overview.json
        timeline.json
        temporal.json
        genres.json
        geography.json
        artist-monthly.json
        discoveries-detailed.json
        artists.json          (search index)
        albums.json            (search index)
        /artists
            index.json         (all artists, sorted by plays)
            {id}.json          (individual artist detail files)
        /albums
            index.json         (all albums, sorted by plays)
        /tracks
            index.json         (all tracks, sorted by plays)
        /story
            2024.json
            ...
        listening.db           (slim database for generation scripts)
"""

import sqlite3
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ============================================
# Configuration
# ============================================

# Export all items - no limits
STORY_YEARS = None  # Auto-detect from data, or set like [2020, 2021, 2022, 2023, 2024]

# Tables to include in slim database
SLIM_DB_TABLES = [
    'canonical_artists',
    'canonical_albums', 
    'canonical_tracks',
    'canonical_track_artists',
    'canonical_track_albums',
    'artist_analytics',
    'album_analytics',
    'track_analytics',
    'artist_genres',
    'monthly_summary',
    'hourly_distribution',
    'weekday_distribution',
    'geographic_analytics',
    'discovery_context',
    'listening_eras',
]

# ============================================
# Helpers
# ============================================

def dict_factory(cursor, row):
    """Convert SQLite rows to dictionaries."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def connect_db(db_path):
    """Connect to SQLite database with dict row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = dict_factory
    return conn


def write_json(data, path):
    """Write data to JSON file with compact formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
    size_kb = path.stat().st_size / 1024
    print(f"  ✓ {path.name} ({size_kb:.1f} KB)")


def ms_to_hours(ms):
    """Convert milliseconds to hours."""
    return round(ms / 3600000, 1) if ms else 0


# ============================================
# Export Functions
# ============================================

def export_overview(conn, output_dir):
    """Export overview stats for homepage."""
    print("\n📊 Exporting overview stats...")
    
    cur = conn.cursor()
    
    # Total stats from analytics tables
    cur.execute("SELECT SUM(total_plays) as plays, SUM(total_duration_ms) as duration FROM artist_analytics")
    totals = cur.fetchone()
    
    cur.execute("SELECT COUNT(*) as count FROM canonical_artists")
    artist_count = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) as count FROM canonical_albums")
    album_count = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) as count FROM canonical_tracks")
    track_count = cur.fetchone()['count']
    
    # Date range
    cur.execute("""
        SELECT MIN(first_play_date) as first, MAX(last_play_date) as last 
        FROM artist_analytics 
        WHERE first_play_date IS NOT NULL
    """)
    dates = cur.fetchone()
    
    # Top artist
    cur.execute("""
        SELECT ca.id, ca.name, aa.total_plays, aa.total_duration_ms
        FROM artist_analytics aa
        JOIN canonical_artists ca ON aa.artist_id = ca.id
        ORDER BY aa.total_plays DESC
        LIMIT 1
    """)
    top_artist = cur.fetchone()
    
    # Top album
    cur.execute("""
        SELECT cab.id, cab.title, ca.name as artist_name, aba.total_plays, aba.total_duration_ms
        FROM album_analytics aba
        JOIN canonical_albums cab ON aba.album_id = cab.id
        LEFT JOIN canonical_artists ca ON cab.primary_artist_id = ca.id
        ORDER BY aba.total_plays DESC
        LIMIT 1
    """)
    top_album = cur.fetchone()
    
    # Top track
    cur.execute("""
        SELECT ct.id, ct.title, ca.name as artist_name, ta.total_plays, ta.total_duration_ms
        FROM track_analytics ta
        JOIN canonical_tracks ct ON ta.track_id = ct.id
        LEFT JOIN canonical_artists ca ON ct.primary_artist_id = ca.id
        ORDER BY ta.total_plays DESC
        LIMIT 1
    """)
    top_track = cur.fetchone()
    
    overview = {
        'totalPlays': totals['plays'] or 0,
        'totalDurationMs': totals['duration'] or 0,
        'totalDurationHours': ms_to_hours(totals['duration']),
        'totalArtists': artist_count,
        'totalAlbums': album_count,
        'totalTracks': track_count,
        'firstPlay': dates['first'],
        'lastPlay': dates['last'],
        'topArtist': {
            'id': top_artist['id'],
            'name': top_artist['name'],
            'plays': top_artist['total_plays'],
        } if top_artist else None,
        'topAlbum': {
            'id': top_album['id'],
            'title': top_album['title'],
            'artistName': top_album['artist_name'],
            'plays': top_album['total_plays'],
        } if top_album else None,
        'topTrack': {
            'id': top_track['id'],
            'title': top_track['title'],
            'artistName': top_track['artist_name'],
            'plays': top_track['total_plays'],
        } if top_track else None,
        'exportedAt': datetime.now().isoformat(),
    }
    
    write_json(overview, output_dir / 'overview.json')
    return overview


def export_timeline(conn, output_dir):
    """Export monthly timeline data with top artists."""
    print("\n📅 Exporting timeline...")
    
    cur = conn.cursor()
    
    # Get monthly summaries
    cur.execute("""
        SELECT 
            ms.year_month,
            ms.total_plays,
            ms.total_duration_ms,
            ms.unique_artists,
            ms.unique_albums,
            ms.unique_tracks,
            ms.new_artists_discovered,
            ms.top_artist_id,
            ms.top_artist_plays,
            ms.fragmentation_score,
            ca.name as top_artist_name
        FROM monthly_summary ms
        LEFT JOIN canonical_artists ca ON ms.top_artist_id = ca.id
        ORDER BY ms.year_month ASC
    """)
    rows = cur.fetchall()
    
    # Get top 20 artists per month
    cur.execute("""
        SELECT 
            strftime('%Y-%m', p.play_timestamp_utc) as year_month,
            ca.id as artist_id,
            ca.name as artist_name,
            COUNT(*) as plays,
            SUM(p.duration_ms) as duration_ms
        FROM plays p
        JOIN canonical_artists ca ON p.primary_artist_id = ca.id
        GROUP BY year_month, ca.id
        ORDER BY year_month, plays DESC
    """)
    artist_rows = cur.fetchall()
    
    # Group artists by month (all artists, not just top 20)
    artists_by_month = {}
    for ar in artist_rows:
        ym = ar['year_month']
        if ym not in artists_by_month:
            artists_by_month[ym] = []
        artists_by_month[ym].append({
            'id': ar['artist_id'],
            'name': ar['artist_name'],
            'plays': ar['plays'],
            'durationMs': ar['duration_ms'],
        })
    
    timeline = []
    for row in rows:
        ym = row['year_month']
        timeline.append({
            'yearMonth': ym,
            'plays': row['total_plays'],
            'durationMs': row['total_duration_ms'],
            'durationHours': ms_to_hours(row['total_duration_ms']),
            'uniqueArtists': row['unique_artists'],
            'uniqueAlbums': row['unique_albums'],
            'uniqueTracks': row['unique_tracks'],
            'newDiscoveries': row['new_artists_discovered'],
            'topArtist': {
                'id': row['top_artist_id'],
                'name': row['top_artist_name'],
                'plays': row['top_artist_plays'],
            } if row['top_artist_id'] else None,
            'topArtists': artists_by_month.get(ym, []),
            'fragmentationScore': row['fragmentation_score'],
        })
    
    write_json(timeline, output_dir / 'timeline.json')
    return timeline


def export_temporal(conn, output_dir):
    """Export hourly and weekday distribution."""
    print("\n🕐 Exporting temporal patterns...")
    
    cur = conn.cursor()
    
    # Hourly
    cur.execute("SELECT * FROM hourly_distribution ORDER BY hour ASC")
    hourly = cur.fetchall()
    
    # Weekday
    cur.execute("SELECT * FROM weekday_distribution ORDER BY weekday ASC")
    weekday = cur.fetchall()
    
    # Calculate insights
    peak_hour = max(hourly, key=lambda x: x['total_plays'])['hour'] if hourly else 0
    peak_day = max(weekday, key=lambda x: x['total_plays'])['weekday'] if weekday else 0
    
    # Night owl score (10pm-4am plays as % of total)
    night_plays = sum(h['total_plays'] for h in hourly if h['hour'] >= 22 or h['hour'] < 4)
    total_plays = sum(h['total_plays'] for h in hourly)
    night_owl_score = round(night_plays / total_plays, 3) if total_plays > 0 else 0
    
    # Weekend warrior (Sat+Sun as % of total)
    weekend_plays = sum(d['total_plays'] for d in weekday if d['weekday'] in [0, 6])  # 0=Sun, 6=Sat
    total_weekly = sum(d['total_plays'] for d in weekday)
    weekend_score = round(weekend_plays / total_weekly, 3) if total_weekly > 0 else 0
    
    temporal = {
        'hourly': [{
            'hour': h['hour'],
            'plays': h['total_plays'],
            'avgPerDay': h['avg_plays_per_day'],
        } for h in hourly],
        'weekday': [{
            'day': d['weekday'],
            'plays': d['total_plays'],
            'avgPerWeek': d['avg_plays_per_week'],
        } for d in weekday],
        'insights': {
            'peakHour': peak_hour,
            'peakDay': peak_day,
            'nightOwlScore': night_owl_score,
            'weekendWarriorScore': weekend_score,
        }
    }
    
    write_json(temporal, output_dir / 'temporal.json')
    return temporal


def export_genres(conn, output_dir):
    """Export genre breakdown."""
    print("\n🎸 Exporting genres...")
    
    cur = conn.cursor()
    
    # Aggregate genres with play counts
    cur.execute("""
        SELECT 
            ag.genre,
            COUNT(DISTINCT ag.canonical_artist_id) as artist_count,
            SUM(aa.total_plays) as total_plays,
            SUM(aa.total_duration_ms) as total_duration_ms
        FROM artist_genres ag
        JOIN artist_analytics aa ON ag.canonical_artist_id = aa.artist_id
        GROUP BY ag.genre
        ORDER BY total_plays DESC
    """)
    genre_stats = cur.fetchall()
    
    total_plays = sum(g['total_plays'] for g in genre_stats)
    
    genres = []
    for g in genre_stats:  # All genres
        # Get top 5 artists for this genre
        cur.execute("""
            SELECT ca.id, ca.name, aa.total_plays
            FROM artist_genres ag
            JOIN canonical_artists ca ON ag.canonical_artist_id = ca.id
            JOIN artist_analytics aa ON ca.id = aa.artist_id
            WHERE ag.genre = ?
            ORDER BY aa.total_plays DESC
            LIMIT 5
        """, (g['genre'],))
        top_artists = cur.fetchall()
        
        genres.append({
            'genre': g['genre'],
            'plays': g['total_plays'],
            'durationMs': g['total_duration_ms'],
            'artistCount': g['artist_count'],
            'percentage': round(g['total_plays'] / total_plays, 4) if total_plays > 0 else 0,
            'topArtists': [{
                'id': a['id'],
                'name': a['name'],
                'plays': a['total_plays'],
            } for a in top_artists]
        })
    
    write_json(genres, output_dir / 'genres.json')
    return genres


def export_discoveries(conn, output_dir):
    """Export discovery data."""
    print("\n🔍 Exporting discoveries...")
    
    cur = conn.cursor()
    
    # Discovery timeline by month
    cur.execute("""
        SELECT year_month, new_artists_discovered
        FROM monthly_summary
        ORDER BY year_month ASC
    """)
    timeline = cur.fetchall()
    
    # Gateway artists
    cur.execute("""
        SELECT 
            ca.id, ca.name, 
            COUNT(dc.discovered_artist_id) as discoveries_triggered,
            aa.total_plays
        FROM discovery_context dc
        JOIN canonical_artists ca ON dc.context_artist_id = ca.id
        JOIN artist_analytics aa ON ca.id = aa.artist_id
        WHERE dc.context_type = 'before'
        GROUP BY dc.context_artist_id
        ORDER BY discoveries_triggered DESC
    """)
    gateways = cur.fetchall()
    
    # Recent discoveries (artists first played in last 2 years)
    cur.execute("""
        SELECT ca.id, ca.name, aa.first_play_date, aa.total_plays
        FROM artist_analytics aa
        JOIN canonical_artists ca ON aa.artist_id = ca.id
        WHERE aa.first_play_date >= date('now', '-2 years')
        ORDER BY aa.first_play_date DESC
    """)
    recent = cur.fetchall()
    
    total_discoveries = sum(t['new_artists_discovered'] for t in timeline)
    years_active = len(set(t['year_month'][:4] for t in timeline))
    
    discoveries = {
        'totalDiscoveries': total_discoveries,
        'avgPerYear': round(total_discoveries / years_active, 1) if years_active > 0 else 0,
        'timeline': [{
            'yearMonth': t['year_month'],
            'count': t['new_artists_discovered'],
        } for t in timeline],
        'gatewayArtists': [{
            'id': g['id'],
            'name': g['name'],
            'discoveriesTriggered': g['discoveries_triggered'],
            'plays': g['total_plays'],
        } for g in gateways],
        'recentDiscoveries': [{
            'id': r['id'],
            'name': r['name'],
            'firstPlayed': r['first_play_date'],
            'plays': r['total_plays'],
        } for r in recent],
    }
    
    # Note: discoveries-detailed.json is generated separately with enriched data
    return discoveries


def export_geography(conn, output_dir):
    """Export geographic data if available."""
    print("\n🌍 Exporting geography...")
    
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT country, region, city, total_plays, first_play_date, last_play_date
            FROM geographic_analytics
            ORDER BY total_plays DESC
        """)
        rows = cur.fetchall()
        
        if not rows:
            print("  ⚠ No geographic data found")
            geography = {'locations': [], 'hasData': False}
        else:
            geography = {
                'hasData': True,
                'locations': [{
                    'country': r['country'],
                    'region': r['region'],
                    'city': r['city'],
                    'plays': r['total_plays'],
                    'firstPlay': r['first_play_date'],
                    'lastPlay': r['last_play_date'],
                } for r in rows]
            }
    except sqlite3.OperationalError:
        print("  ⚠ Geographic table not found")
        geography = {'locations': [], 'hasData': False}
    
    write_json(geography, output_dir / 'geography.json')
    return geography


def export_artist_monthly(conn, output_dir):
    """Export monthly play counts for all artists."""
    print("\n📈 Exporting artist monthly data...")
    
    cur = conn.cursor()
    
    # Get monthly plays for all artists from the plays table
    cur.execute("""
        SELECT 
            p.primary_artist_id as artist_id,
            ca.name as artist_name,
            strftime('%Y-%m', p.play_timestamp_utc) as year_month,
            COUNT(*) as plays,
            SUM(COALESCE(p.duration_ms, p.ms_played, 0)) as duration_ms
        FROM plays p
        JOIN canonical_artists ca ON p.primary_artist_id = ca.id
        WHERE p.primary_artist_id IS NOT NULL 
          AND p.is_duplicate = 0
        GROUP BY p.primary_artist_id, year_month
        ORDER BY p.primary_artist_id, year_month
    """)
    rows = cur.fetchall()
    
    # Group by artist for efficient lookup
    artist_monthly = {}
    for r in rows:
        artist_id = r['artist_id']
        if artist_id not in artist_monthly:
            artist_monthly[artist_id] = {
                'artistId': artist_id,
                'artistName': r['artist_name'],
                'months': []
            }
        artist_monthly[artist_id]['months'].append({
            'yearMonth': r['year_month'],
            'plays': r['plays'],
            'durationMs': r['duration_ms'],
        })
    
    # Convert to list sorted by total plays
    artist_totals = []
    for artist_id, data in artist_monthly.items():
        total_plays = sum(m['plays'] for m in data['months'])
        artist_totals.append((total_plays, data))
    
    artist_totals.sort(reverse=True, key=lambda x: x[0])
    result = [data for _, data in artist_totals]
    
    write_json(result, output_dir / 'artist-monthly.json')
    print(f"  Artists with monthly data: {len(result):,}, Total month records: {len(rows):,}")
    return result


def export_search_indexes(conn, output_dir):
    """Export search indexes for Fuse.js (root level files)."""
    print("\n🔎 Exporting search indexes...")
    
    cur = conn.cursor()
    
    # Artists search index
    cur.execute("""
        SELECT ca.id, ca.name, ca.sort_name, aa.total_plays
        FROM canonical_artists ca
        LEFT JOIN artist_analytics aa ON ca.id = aa.artist_id
        ORDER BY aa.total_plays DESC NULLS LAST
    """)
    artists = [{
        'id': r['id'],
        'name': r['name'],
        'sortName': r['sort_name'],
        'plays': r['total_plays'] or 0,
    } for r in cur.fetchall()]
    write_json(artists, output_dir / 'artists.json')
    
    # Albums search index
    cur.execute("""
        SELECT cab.id, cab.title, ca.id as artist_id, ca.name as artist_name, aba.total_plays
        FROM canonical_albums cab
        LEFT JOIN canonical_artists ca ON cab.primary_artist_id = ca.id
        LEFT JOIN album_analytics aba ON cab.id = aba.album_id
        ORDER BY aba.total_plays DESC NULLS LAST
    """)
    albums = [{
        'id': r['id'],
        'title': r['title'],
        'artistId': r['artist_id'],
        'artistName': r['artist_name'],
        'plays': r['total_plays'] or 0,
    } for r in cur.fetchall()]
    write_json(albums, output_dir / 'albums.json')
    
    print(f"  Artists: {len(artists):,}, Albums: {len(albums):,}")


def export_top_lists(conn, output_dir):
    """Export top artists/albums/tracks as index.json files."""
    print("\n🏆 Exporting top lists...")
    
    cur = conn.cursor()
    
    # All artists with genres (sorted by plays)
    cur.execute("""
        SELECT 
            ca.id, ca.name, ca.country, ca.artist_type,
            aa.total_plays, aa.total_duration_ms, aa.unique_tracks_played, 
            aa.first_play_date, aa.last_play_date
        FROM artist_analytics aa
        JOIN canonical_artists ca ON aa.artist_id = ca.id
        ORDER BY aa.total_plays DESC
    """)
    artists_raw = cur.fetchall()
    
    artists = []
    for a in artists_raw:
        # Get genres for this artist
        cur.execute("""
            SELECT genre FROM artist_genres 
            WHERE canonical_artist_id = ? 
            ORDER BY match_confidence DESC 
            LIMIT 5
        """, (a['id'],))
        genres = [g['genre'] for g in cur.fetchall()]
        
        artists.append({
            'id': a['id'],
            'name': a['name'],
            'country': a['country'],
            'type': a['artist_type'],
            'plays': a['total_plays'],
            'durationMs': a['total_duration_ms'],
            'durationHours': ms_to_hours(a['total_duration_ms']),
            'uniqueTracks': a['unique_tracks_played'],
            'firstPlay': a['first_play_date'],
            'lastPlay': a['last_play_date'],
            'genres': genres,
        })
    write_json(artists, output_dir / 'artists' / 'index.json')
    
    # All albums (sorted by plays)
    cur.execute("""
        SELECT 
            cab.id, cab.title, cab.release_year, cab.album_type,
            ca.id as artist_id, ca.name as artist_name,
            aba.total_plays, aba.total_duration_ms, aba.unique_tracks_played,
            aba.first_play_date, aba.last_play_date, aba.completion_rate
        FROM album_analytics aba
        JOIN canonical_albums cab ON aba.album_id = cab.id
        LEFT JOIN canonical_artists ca ON cab.primary_artist_id = ca.id
        ORDER BY aba.total_plays DESC
    """)
    albums = [{
        'id': r['id'],
        'title': r['title'],
        'releaseYear': r['release_year'],
        'albumType': r['album_type'],
        'artistId': r['artist_id'],
        'artistName': r['artist_name'],
        'plays': r['total_plays'],
        'durationMs': r['total_duration_ms'],
        'durationHours': ms_to_hours(r['total_duration_ms']),
        'uniqueTracks': r['unique_tracks_played'],
        'firstPlay': r['first_play_date'],
        'lastPlay': r['last_play_date'],
        'completionRate': r['completion_rate'],
    } for r in cur.fetchall()]
    write_json(albums, output_dir / 'albums' / 'index.json')
    
    # All tracks (sorted by plays)
    cur.execute("""
        SELECT 
            ct.id, ct.title, ct.duration_ms,
            ca.id as artist_id, ca.name as artist_name,
            cab.id as album_id, cab.title as album_title,
            ta.total_plays, ta.total_duration_ms, ta.first_play_date, ta.last_play_date
        FROM track_analytics ta
        JOIN canonical_tracks ct ON ta.track_id = ct.id
        LEFT JOIN canonical_artists ca ON ct.primary_artist_id = ca.id
        LEFT JOIN canonical_albums cab ON ct.primary_album_id = cab.id
        ORDER BY ta.total_plays DESC
    """)
    tracks = [{
        'id': r['id'],
        'title': r['title'],
        'durationMs': r['duration_ms'],
        'artistId': r['artist_id'],
        'artistName': r['artist_name'],
        'albumId': r['album_id'],
        'albumTitle': r['album_title'],
        'plays': r['total_plays'],
        'totalDurationMs': r['total_duration_ms'],
        'totalDurationHours': ms_to_hours(r['total_duration_ms']),
        'firstPlay': r['first_play_date'],
        'lastPlay': r['last_play_date'],
    } for r in cur.fetchall()]
    write_json(tracks, output_dir / 'tracks' / 'index.json')


def export_story_data(conn, output_dir, years=None):
    """Export year-in-review story data."""
    print("\n✨ Exporting story data...")
    
    cur = conn.cursor()
    story_dir = output_dir / 'story'
    
    # Get available years
    if years is None:
        cur.execute("SELECT DISTINCT substr(year_month, 1, 4) as year FROM monthly_summary ORDER BY year DESC")
        years = [int(r['year']) for r in cur.fetchall()]
    
    for year in years:
        year_str = str(year)
        
        # Year totals
        cur.execute("""
            SELECT 
                SUM(total_plays) as plays,
                SUM(total_duration_ms) as duration,
                SUM(unique_artists) as artists,
                SUM(new_artists_discovered) as discoveries
            FROM monthly_summary
            WHERE year_month LIKE ?
        """, (f"{year_str}%",))
        totals = cur.fetchone()
        
        if not totals['plays']:
            continue
        
        # Top artist of year
        cur.execute("""
            SELECT ca.id, ca.name, SUM(ms.top_artist_plays) as plays
            FROM monthly_summary ms
            JOIN canonical_artists ca ON ms.top_artist_id = ca.id
            WHERE ms.year_month LIKE ?
            GROUP BY ms.top_artist_id
            ORDER BY plays DESC
            LIMIT 1
        """, (f"{year_str}%",))
        top_artist = cur.fetchone()
        
        # Top track (need to query track_analytics with date filter)
        cur.execute("""
            SELECT ct.id, ct.title, ca.name as artist_name, ta.total_plays
            FROM track_analytics ta
            JOIN canonical_tracks ct ON ta.track_id = ct.id
            LEFT JOIN canonical_artists ca ON ct.primary_artist_id = ca.id
            WHERE ta.first_play_date LIKE ? OR ta.last_play_date LIKE ?
            ORDER BY ta.total_plays DESC
            LIMIT 1
        """, (f"{year_str}%", f"{year_str}%"))
        top_track = cur.fetchone()
        
        # Build story slides
        slides = [
            {
                'id': 'intro',
                'type': 'intro',
                'title': f'Your {year} in Music',
                'subtitle': 'Let\'s look back at the year',
                'gradient': 'story-1',
            },
            {
                'id': 'total-plays',
                'type': 'stat',
                'value': totals['plays'],
                'label': 'songs played',
                'gradient': 'story-2',
            },
            {
                'id': 'listening-time',
                'type': 'stat',
                'value': round(totals['duration'] / 3600000),
                'label': 'hours of music',
                'subtitle': f"That's {round(totals['duration'] / 3600000 / 24)} days of non-stop listening",
                'gradient': 'story-3',
            },
            {
                'id': 'top-artist',
                'type': 'artist',
                'title': 'Your #1 Artist',
                'entity': {
                    'id': top_artist['id'],
                    'name': top_artist['name'],
                    'plays': top_artist['plays'],
                } if top_artist else None,
                'gradient': 'story-1',
            },
            {
                'id': 'discoveries',
                'type': 'stat',
                'value': totals['discoveries'],
                'label': 'new artists discovered',
                'gradient': 'story-2',
            },
        ]
        
        if top_track:
            slides.append({
                'id': 'top-track',
                'type': 'track',
                'title': 'Your Top Track',
                'entity': {
                    'id': top_track['id'],
                    'title': top_track['title'],
                    'artistName': top_track['artist_name'],
                    'plays': top_track['total_plays'],
                },
                'gradient': 'story-3',
            })
        
        slides.append({
            'id': 'outro',
            'type': 'outro',
            'title': f'That was your {year}',
            'subtitle': 'Here\'s to more music ahead',
            'gradient': 'story-1',
        })
        
        story = {
            'year': year,
            'slides': slides,
            'generatedAt': datetime.now().isoformat(),
        }
        
        write_json(story, story_dir / f'{year}.json')
    
    print(f"  Generated stories for {len(years)} years")


def export_artist_details(conn, output_dir, artist_monthly_data):
    """Export individual artist detail files with timeline data."""
    print("\n👤 Exporting artist detail files...")
    
    cur = conn.cursor()
    artists_dir = output_dir / 'artists'
    
    # Load artist index to get all artists
    cur.execute("""
        SELECT 
            ca.id, ca.name, ca.country, ca.artist_type,
            aa.total_plays, aa.total_duration_ms, aa.unique_tracks_played,
            aa.first_play_date, aa.last_play_date
        FROM artist_analytics aa
        JOIN canonical_artists ca ON aa.artist_id = ca.id
        ORDER BY aa.total_plays DESC
    """)
    artists = cur.fetchall()
    
    # Create lookup for monthly data
    monthly_by_artist = {}
    for entry in artist_monthly_data:
        monthly_by_artist[entry['artistId']] = entry['months']
    
    generated = 0
    for a in artists:
        monthly_data = monthly_by_artist.get(a['id'], [])
        
        # Build monthly timeline
        monthly_timeline = [{
            'month': m['yearMonth'],
            'plays': m['plays'],
            'durationMs': m['durationMs'],
        } for m in monthly_data]
        
        # Build yearly summary
        yearly_map = {}
        for m in monthly_timeline:
            year = int(m['month'].split('-')[0])
            if year not in yearly_map:
                yearly_map[year] = {'plays': 0, 'durationMs': 0}
            yearly_map[year]['plays'] += m['plays']
            yearly_map[year]['durationMs'] += m['durationMs']
        
        yearly_timeline = [
            {'year': year, 'plays': data['plays'], 'durationMs': data['durationMs']}
            for year, data in sorted(yearly_map.items())
        ]
        
        # Find peaks
        peak_month = max(monthly_timeline, key=lambda x: x['plays']) if monthly_timeline else None
        peak_year = max(yearly_timeline, key=lambda x: x['plays']) if yearly_timeline else None
        
        artist_detail = {
            'id': a['id'],
            'name': a['name'],
            'country': a['country'],
            'type': a['artist_type'],
            'plays': a['total_plays'],
            'durationHours': ms_to_hours(a['total_duration_ms']),
            'uniqueTracks': a['unique_tracks_played'],
            'firstPlay': a['first_play_date'],
            'lastPlay': a['last_play_date'],
            'peakYear': peak_year['year'] if peak_year else None,
            'peakMonth': peak_month['month'] if peak_month else None,
            'monthlyTimeline': monthly_timeline,
            'yearlyTimeline': yearly_timeline,
            'topAlbums': [],
            'topTracks': [],
        }
        
        write_json(artist_detail, artists_dir / f"{a['id']}.json")
        generated += 1
    
    print(f"  Generated {generated:,} artist detail files")


def export_discoveries_detailed(conn, output_dir):
    """Export enriched discoveries data with per-year artist lists."""
    print("\n🔍 Exporting discoveries-detailed.json...")
    
    cur = conn.cursor()
    
    # Get all artist discoveries with first play date
    cur.execute("""
        SELECT 
            ca.id as artist_id,
            ca.name as artist_name,
            aa.first_play_date,
            aa.total_plays
        FROM artist_analytics aa
        JOIN canonical_artists ca ON ca.id = aa.artist_id
        WHERE aa.first_play_date IS NOT NULL
        ORDER BY aa.first_play_date ASC
    """)
    all_discoveries = cur.fetchall()
    
    # Group by year-month and year
    by_year_month = defaultdict(list)
    by_year = defaultdict(list)
    
    for d in all_discoveries:
        year_month = d['first_play_date'][:7]
        year = int(d['first_play_date'][:4])
        
        entry = {
            'id': d['artist_id'],
            'name': d['artist_name'],
            'firstPlayed': d['first_play_date'],
            'plays': d['total_plays'],
        }
        by_year_month[year_month].append(entry)
        by_year[year].append(entry)
    
    # Build monthly timeline
    monthly_timeline = []
    for year_month in sorted(by_year_month.keys()):
        artists = by_year_month[year_month]
        monthly_timeline.append({
            'yearMonth': year_month,
            'count': len(artists),
            'artists': sorted(artists, key=lambda x: -x['plays']),
        })
    
    # Build yearly timeline
    yearly_timeline = []
    for year in sorted(by_year.keys(), reverse=True):
        artists = by_year[year]
        yearly_timeline.append({
            'year': year,
            'count': len(artists),
            'topArtists': sorted(artists, key=lambda x: -x['plays'])[:10],
            'allArtists': sorted(artists, key=lambda x: x['firstPlayed']),
        })
    
    # Recent discoveries
    recent_discoveries = [
        {'id': d['artist_id'], 'name': d['artist_name'], 
         'firstPlayed': d['first_play_date'], 'plays': d['total_plays']}
        for d in all_discoveries[-50:]
    ][::-1]
    
    # Stats
    total_discoveries = len(all_discoveries)
    years_active = len(by_year)
    avg_per_year = round(total_discoveries / years_active, 1) if years_active else 0
    
    peak_month = max(monthly_timeline, key=lambda x: x['count']) if monthly_timeline else {'yearMonth': '', 'count': 0}
    
    # Gateway artists
    cur.execute("""
        SELECT 
            ca.id, ca.name,
            COUNT(DISTINCT dc.discovered_artist_id) as introduced_count
        FROM discovery_context dc
        JOIN canonical_artists ca ON ca.id = dc.context_artist_id
        WHERE dc.context_type = 'before'
        GROUP BY dc.context_artist_id
        ORDER BY introduced_count DESC
        LIMIT 20
    """)
    gateway_artists = [{'id': g['id'], 'name': g['name'], 'introducedCount': g['introduced_count']} 
                       for g in cur.fetchall()]
    
    output = {
        'totalDiscoveries': total_discoveries,
        'avgPerYear': avg_per_year,
        'yearsActive': years_active,
        'peakMonth': {'yearMonth': peak_month['yearMonth'], 'count': peak_month['count']},
        'recentDiscoveries': recent_discoveries,
        'yearlyTimeline': yearly_timeline,
        'monthlyTimeline': monthly_timeline,
        'gatewayArtists': gateway_artists,
    }
    
    write_json(output, output_dir / 'discoveries-detailed.json')


def create_slim_database(source_conn, output_path):
    """Create a slim database with only dimension and analytics tables."""
    print("\n💾 Creating slim database...")
    
    # Remove existing slim DB if present
    if output_path.exists():
        output_path.unlink()
    
    # Create new database
    slim_conn = sqlite3.connect(output_path)
    slim_cur = slim_conn.cursor()
    source_cur = source_conn.cursor()
    
    # Get list of tables in source
    source_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    available_tables = {row['name'] for row in source_cur.fetchall()}
    
    tables_copied = 0
    rows_copied = 0
    
    for table in SLIM_DB_TABLES:
        if table not in available_tables:
            print(f"  ⚠ Table '{table}' not found, skipping")
            continue
        
        # Get table schema
        source_cur.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'")
        schema = source_cur.fetchone()
        if not schema:
            continue
        
        # Create table in slim DB
        slim_cur.execute(schema['sql'])
        
        # Copy data - get column names to preserve order
        source_cur.execute(f"PRAGMA table_info({table})")
        columns = [col['name'] for col in source_cur.fetchall()]
        
        source_cur.execute(f"SELECT * FROM {table}")
        rows = source_cur.fetchall()
        
        if rows:
            placeholders = ','.join(['?' for _ in range(len(columns))])
            # Convert dict rows to tuples in column order
            row_tuples = [tuple(row[col] for col in columns) for row in rows]
            slim_cur.executemany(f"INSERT INTO {table} VALUES ({placeholders})", row_tuples)
            rows_copied += len(rows)
        
        tables_copied += 1
        print(f"  ✓ {table}: {len(rows):,} rows")
    
    # Copy indexes for tables we included
    source_cur.execute("SELECT sql, tbl_name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")
    for row in source_cur.fetchall():
        if row['tbl_name'] in available_tables and row['tbl_name'] in SLIM_DB_TABLES:
            try:
                slim_cur.execute(row['sql'])
            except sqlite3.OperationalError:
                pass  # Index might reference missing table
    
    slim_conn.commit()
    slim_conn.close()
    
    # Report size
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n  📦 Slim database: {size_mb:.1f} MB ({tables_copied} tables, {rows_copied:,} rows)")


# ============================================
# Main
# ============================================

def main():
    if len(sys.argv) < 3:
        print("Usage: python export_data.py <source_db_path> <output_dir>")
        print("Example: python export_data.py ~/listening.db ./public/data")
        sys.exit(1)
    
    source_db = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    
    if not source_db.exists():
        print(f"❌ Source database not found: {source_db}")
        sys.exit(1)
    
    print(f"📀 Source database: {source_db}")
    print(f"📁 Output directory: {output_dir}")
    
    # Create output directories
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'artists').mkdir(exist_ok=True)
    (output_dir / 'albums').mkdir(exist_ok=True)
    (output_dir / 'tracks').mkdir(exist_ok=True)
    (output_dir / 'story').mkdir(exist_ok=True)
    
    # Connect to source database
    conn = connect_db(source_db)
    
    try:
        # Export JSON files
        export_overview(conn, output_dir)
        export_timeline(conn, output_dir)
        export_temporal(conn, output_dir)
        export_genres(conn, output_dir)
        export_discoveries(conn, output_dir)  # Basic discoveries (not written, just returned)
        export_geography(conn, output_dir)
        artist_monthly = export_artist_monthly(conn, output_dir)
        export_search_indexes(conn, output_dir)
        export_top_lists(conn, output_dir)
        export_story_data(conn, output_dir, STORY_YEARS)
        export_discoveries_detailed(conn, output_dir)
        export_artist_details(conn, output_dir, artist_monthly)
        
        # Create slim database (optional, for any scripts that still need it)
        create_slim_database(conn, output_dir / 'listening.db')
        
        print("\n✅ Export complete!")
        
        # Summary
        json_size = sum(f.stat().st_size for f in output_dir.rglob('*.json')) / 1024
        db_size = (output_dir / 'listening.db').stat().st_size / (1024 * 1024)
        print(f"\n📊 Total JSON: {json_size:.1f} KB")
        print(f"💾 Slim database: {db_size:.1f} MB")
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()
