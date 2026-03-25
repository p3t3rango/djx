#!/usr/bin/env python3
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from soundcloud import SoundCloud

from core.config import GENRES, get_int_setting
from core.database import Database
from core.discovery_service import DiscoveryService
from core.download_service import DownloadService
from core.search_service import SearchService
from core.utils import format_duration, format_play_count

console = Console()


def interactive_genre_select() -> tuple:
    console.print(Panel(
        "[bold]SoundCloud Track Discoverer & Downloader[/bold]\n"
        "Find trending tracks by genre and download them.",
        title="DJX v2",
        border_style="cyan",
    ))

    genre_keys = list(GENRES.keys())
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Num", style="cyan bold", width=4)
    table.add_column("Genre", style="white")
    for i, key in enumerate(genre_keys, 1):
        table.add_row(str(i), GENRES[key]["display_name"])
    console.print(table)
    console.print()

    selection = console.input("[cyan]Select genres (comma-separated numbers, or 'all'): [/cyan]").strip()

    if selection.lower() == "all":
        selected = genre_keys
    else:
        try:
            indices = [int(x.strip()) - 1 for x in selection.split(",")]
            selected = [genre_keys[i] for i in indices if 0 <= i < len(genre_keys)]
        except (ValueError, IndexError):
            console.print("[red]Invalid selection. Exiting.[/red]")
            sys.exit(1)

    if not selected:
        console.print("[red]No genres selected. Exiting.[/red]")
        sys.exit(1)

    remix_input = console.input("[cyan]Include remixes? [y/N]: [/cyan]").strip().lower()
    include_remixes = remix_input in ("y", "yes")

    console.print()
    console.print("[bold]Selected:[/bold]", ", ".join(GENRES[k]["display_name"] for k in selected))
    if include_remixes:
        console.print("[bold]Remixes:[/bold] Yes")
    console.print()

    confirm = console.input("[cyan]Proceed? [Y/n]: [/cyan]").strip().lower()
    if confirm in ("n", "no"):
        console.print("Cancelled.")
        sys.exit(0)

    return selected, include_remixes


def display_tracks(tracks, genre_name: str):
    table = Table(title=f"{genre_name} - {len(tracks)} tracks found", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="white", max_width=40, no_wrap=True)
    table.add_column("Artist", style="cyan", max_width=25, no_wrap=True)
    table.add_column("Plays", style="green", justify="right")
    table.add_column("Score", style="magenta", justify="right")
    table.add_column("Duration", style="dim", justify="right")

    for i, t in enumerate(tracks[:20], 1):
        table.add_row(
            str(i), t.title[:40], t.artist[:25],
            format_play_count(t.playback_count),
            f"{t.trending_score:.0f}",
            format_duration(t.duration_seconds),
        )

    if len(tracks) > 20:
        table.add_row("...", f"and {len(tracks) - 20} more", "", "", "", "")

    console.print(table)
    console.print()


def run_genre_discovery(discoverer, downloader, genre_key, count, include_remixes, output, summary):
    genre_name = GENRES[genre_key]["display_name"]
    genre_folder = GENRES[genre_key]["folder"]

    # Discover
    console.print(f"\n[bold cyan]Discovering {genre_name} tracks...[/bold cyan]")
    tracks = discoverer.discover_genre(genre_key, target=count,
                                        on_progress=lambda msg: console.print(f"  [dim]{msg}[/dim]"))

    if not tracks:
        console.print(f"[yellow]No tracks found for {genre_name}.[/yellow]")
        summary.append((genre_name, 0, 0, 0, 0))
        return

    display_tracks(tracks, genre_name)

    # Download
    console.print(f"[bold]Downloading to {output}/{genre_folder}/[/bold]")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("Downloading...", total=len(tracks))

        def on_dl_progress(i, total, track):
            short = f"{track.artist} - {track.title}"
            if len(short) > 50:
                short = short[:47] + "..."
            progress.update(task, description=short, completed=i)

        report = downloader.download_tracks(tracks, genre_folder, on_progress=on_dl_progress)
        progress.update(task, completed=len(tracks))

    summary.append((genre_name, len(tracks), report.downloaded, report.skipped, report.failed))
    console.print(
        f"[green]{report.downloaded} downloaded[/green] | "
        f"[yellow]{report.skipped} skipped[/yellow] | "
        f"[red]{report.failed} failed[/red]"
    )

    # Remixes
    if include_remixes:
        console.print(f"\n[bold cyan]Discovering {genre_name} remixes...[/bold cyan]")
        remix_tracks = discoverer.discover_remixes(genre_key, target=count,
                                                    on_progress=lambda msg: console.print(f"  [dim]{msg}[/dim]"))
        if remix_tracks:
            remix_folder = f"{genre_folder}-remixes"
            display_tracks(remix_tracks, f"{genre_name} Remixes")
            console.print(f"[bold]Downloading to {output}/{remix_folder}/[/bold]")

            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                          BarColumn(), TaskProgressColumn(), console=console) as progress:
                task = progress.add_task("Downloading...", total=len(remix_tracks))

                def on_remix_progress(i, total, track):
                    short = f"{track.artist} - {track.title}"
                    if len(short) > 50:
                        short = short[:47] + "..."
                    progress.update(task, description=short, completed=i)

                remix_report = downloader.download_tracks(remix_tracks, remix_folder,
                                                          on_progress=on_remix_progress)
                progress.update(task, completed=len(remix_tracks))

            summary.append((f"{genre_name} Remixes", len(remix_tracks),
                           remix_report.downloaded, remix_report.skipped, remix_report.failed))
            console.print(
                f"[green]{remix_report.downloaded} downloaded[/green] | "
                f"[yellow]{remix_report.skipped} skipped[/yellow] | "
                f"[red]{remix_report.failed} failed[/red]"
            )
        else:
            console.print(f"[yellow]No remix tracks found for {genre_name}.[/yellow]")


def run_artist_search(search_svc, downloader, artist_query, count, output):
    console.print(f"\n[bold cyan]Searching for artist: {artist_query}[/bold cyan]")
    artists = search_svc.search_artists(artist_query, limit=5)

    if not artists:
        console.print("[yellow]No artists found.[/yellow]")
        return

    # Show top results
    for i, a in enumerate(artists[:5], 1):
        console.print(f"  {i}. [cyan]{a.username}[/cyan] ({format_play_count(a.follower_count)} followers, {a.track_count} tracks)")

    # Use the top result
    artist = artists[0]
    console.print(f"\n[bold]Getting tracks from {artist.username}...[/bold]")

    tracks = search_svc.get_artist_tracks(artist.user_id, limit=count)
    if not tracks:
        console.print("[yellow]No tracks found for this artist.[/yellow]")
        return

    display_tracks(tracks, artist.username)

    folder = f"artist-{sanitize_fn(artist.username.lower().replace(' ', '-'))}"
    console.print(f"[bold]Downloading to {output}/{folder}/[/bold]")
    report = downloader.download_tracks(tracks, folder)
    console.print(
        f"[green]{report.downloaded} downloaded[/green] | "
        f"[yellow]{report.skipped} skipped[/yellow] | "
        f"[red]{report.failed} failed[/red]"
    )


def sanitize_fn(name):
    import re
    return re.sub(r'[^a-z0-9-]', '', name)[:30]


def run_track_search(search_svc, downloader, query, count, output):
    console.print(f"\n[bold cyan]Searching tracks: {query}[/bold cyan]")
    tracks = search_svc.search_tracks(query, limit=count)

    if not tracks:
        console.print("[yellow]No tracks found.[/yellow]")
        return

    display_tracks(tracks, f"Search: {query}")

    folder = f"search-{sanitize_fn(query.lower().replace(' ', '-'))}"
    console.print(f"[bold]Downloading to {output}/{folder}/[/bold]")
    report = downloader.download_tracks(tracks, folder)
    console.print(
        f"[green]{report.downloaded} downloaded[/green] | "
        f"[yellow]{report.skipped} skipped[/yellow] | "
        f"[red]{report.failed} failed[/red]"
    )


@click.command()
@click.option("--genre", "-g", multiple=True,
              type=click.Choice(list(GENRES.keys()), case_sensitive=False),
              help="Genres to download. Omit for interactive selection.")
@click.option("--include-remixes", "-r", is_flag=True, default=False,
              help="Also search for remixes within selected genres.")
@click.option("--count", "-n", default=50, show_default=True,
              help="Number of tracks per genre.")
@click.option("--output", "-o", default="downloads", show_default=True,
              help="Base output directory.")
@click.option("--all-genres", "-a", is_flag=True, default=False,
              help="Download all genres.")
@click.option("--search", "-s", default=None,
              help="Search for tracks matching a query.")
@click.option("--artist", "-A", default=None,
              help="Find an artist and download their tracks.")
@click.option("--serve", is_flag=True, default=False,
              help="Start the web UI server.")
def main(genre, include_remixes, count, output, all_genres, search, artist, serve):
    """Discover and download trending SoundCloud tracks by genre."""

    if serve:
        import uvicorn
        console.print("[bold cyan]Starting DJX web UI...[/bold cyan]")
        console.print("Open [link=http://127.0.0.1:8000]http://127.0.0.1:8000[/link] in your browser")
        uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=False)
        return

    # Initialize
    db = Database("sc_discover.db")

    # Migrate old manifests if they exist
    migrated = db.migrate_manifests(output)
    if migrated:
        console.print(f"[dim]Migrated {migrated} tracks from legacy manifests to database.[/dim]")

    try:
        console.print("[dim]Connecting to SoundCloud...[/dim]")
        sc = SoundCloud()
        console.print("[green]Connected.[/green]")
    except Exception as e:
        console.print(f"[red]Failed to connect to SoundCloud: {e}[/red]")
        sys.exit(1)

    discoverer = DiscoveryService(sc, db)
    downloader = DownloadService(sc, db)
    search_svc = SearchService(sc, db)

    try:
        # Artist search mode
        if artist:
            run_artist_search(search_svc, downloader, artist, count, output)
            return

        # Track search mode
        if search:
            run_track_search(search_svc, downloader, search, count, output)
            return

        # Genre discovery mode
        if all_genres:
            selected_genres = list(GENRES.keys())
        elif genre:
            selected_genres = list(genre)
        else:
            selected_genres, include_remixes = interactive_genre_select()

        summary = []
        for genre_key in selected_genres:
            run_genre_discovery(discoverer, downloader, genre_key, count,
                              include_remixes, output, summary)

        # Final summary
        if summary:
            console.print("\n")
            table = Table(title="Download Summary", show_lines=True)
            table.add_column("Genre", style="cyan")
            table.add_column("Found", justify="right")
            table.add_column("Downloaded", justify="right", style="green")
            table.add_column("Skipped", justify="right", style="yellow")
            table.add_column("Failed", justify="right", style="red")

            total_found = total_dl = total_skip = total_fail = 0
            for name, found, dl, skip, fail in summary:
                table.add_row(name, str(found), str(dl), str(skip), str(fail))
                total_found += found
                total_dl += dl
                total_skip += skip
                total_fail += fail

            table.add_row("[bold]Total[/bold]", f"[bold]{total_found}[/bold]",
                         f"[bold]{total_dl}[/bold]", f"[bold]{total_skip}[/bold]",
                         f"[bold]{total_fail}[/bold]")
            console.print(table)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
    finally:
        db.close()

    console.print("\n[bold green]Done![/bold green]")


if __name__ == "__main__":
    main()
