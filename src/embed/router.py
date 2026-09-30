"""Embeddable gallery widget router and public API."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.config import get_settings
from src.database import get_db
from src.events.models import Event
from src.submissions.models import Project

router = APIRouter(tags=["embed"])
settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


EMBED_JS_CODE = """(function() {
  function initGalleryWidgets() {
    var widgets = document.querySelectorAll('#chameleon-gallery-widget, .chameleon-gallery-widget, [data-chameleon-gallery]');
    widgets.forEach(function(container) {
      if (container.getAttribute('data-loaded')) return;
      container.setAttribute('data-loaded', 'true');

      var eventId = container.getAttribute('data-event-id') || container.getAttribute('data-event-slug');
      var limit = container.getAttribute('data-limit') || '12';
      var theme = container.getAttribute('data-theme') || 'verdant';
      var baseUrl = container.getAttribute('data-base-url') || '';

      if (!eventId) {
        container.innerHTML = '<div style="color:red;padding:12px;font-family:sans-serif;">Missing data-event-id attribute</div>';
        return;
      }

      container.innerHTML = '<div style="padding:24px;text-align:center;font-family:sans-serif;color:#64748b;">Loading gallery projects...</div>';

      fetch(baseUrl + '/api/v1/embed/events/' + encodeURIComponent(eventId) + '/projects?limit=' + encodeURIComponent(limit))
        .then(function(res) {
          if (!res.ok) throw new Error('Failed to load gallery projects');
          return res.json();
        })
        .then(function(projects) {
          renderGallery(container, projects, baseUrl, theme);
        })
        .catch(function(err) {
          container.innerHTML = '<div style="padding:16px;color:#ef4444;font-family:sans-serif;">Error loading projects: ' + err.message + '</div>';
        });
    });
  }

  function renderGallery(container, projects, baseUrl, theme) {
    if (!projects || projects.length === 0) {
      container.innerHTML = '<div style="padding:32px;text-align:center;color:#64748b;font-family:sans-serif;">No submitted projects found in this gallery yet.</div>';
      return;
    }

    var styleId = 'chameleon-embed-styles';
    if (!document.getElementById(styleId)) {
      var style = document.createElement('style');
      style.id = styleId;
      style.textContent = `
        .chm-embed-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 20px;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          box-sizing: border-box;
        }
        .chm-embed-card {
          background: #ffffff;
          border: 1px solid #e2e8f0;
          border-radius: 12px;
          padding: 20px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
          transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .chm-embed-card:hover {
          transform: translateY(-2px);
          box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);
        }
        .chm-embed-tag {
          display: inline-block;
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          padding: 3px 8px;
          border-radius: 9999px;
          background: #e2e8f0;
          color: #334155;
          margin-bottom: 12px;
        }
        .chm-embed-title {
          font-size: 18px;
          font-weight: 700;
          color: #0f172a;
          margin: 0 0 8px 0;
          line-height: 1.3;
        }
        .chm-embed-title a {
          color: inherit;
          text-decoration: none;
        }
        .chm-embed-title a:hover {
          color: #2563eb;
        }
        .chm-embed-team {
          font-size: 12px;
          color: #64748b;
          margin-bottom: 10px;
        }
        .chm-embed-tagline {
          font-size: 14px;
          color: #475569;
          line-height: 1.5;
          margin-bottom: 16px;
          flex-grow: 1;
        }
        .chm-embed-links {
          display: flex;
          gap: 10px;
          padding-top: 12px;
          border-top: 1px solid #f1f5f9;
        }
        .chm-embed-link {
          font-size: 12px;
          font-weight: 600;
          color: #2563eb;
          text-decoration: none;
        }
        .chm-embed-link:hover {
          text-decoration: underline;
        }
      `;
      document.head.appendChild(style);
    }

    var html = '<div class="chm-embed-grid">';
    projects.forEach(function(p) {
      var trackHtml = p.track_name ? '<span class="chm-embed-tag">' + escapeHtml(p.track_name) + '</span>' : '';
      var teamHtml = p.team_name ? '<div class="chm-embed-team">By ' + escapeHtml(p.team_name) + '</div>' : '';
      var projectUrl = baseUrl + '/projects/' + encodeURIComponent(p.id);

      html += '<div class="chm-embed-card">';
      html += '  <div>';
      html += '    ' + trackHtml;
      html += '    <h3 class="chm-embed-title"><a href="' + projectUrl + '" target="_blank">' + escapeHtml(p.title) + '</a></h3>';
      html += '    ' + teamHtml;
      html += '    <p class="chm-embed-tagline">' + escapeHtml(p.tagline || p.description || '') + '</p>';
      html += '  </div>';
      html += '  <div class="chm-embed-links">';
      html += '    <a class="chm-embed-link" href="' + projectUrl + '" target="_blank">View Project &rarr;</a>';
      if (p.demo_url) {
        html += '    <a class="chm-embed-link" href="' + escapeHtml(p.demo_url) + '" target="_blank">Demo</a>';
      }
      if (p.repository_url) {
        html += '    <a class="chm-embed-link" href="' + escapeHtml(p.repository_url) + '" target="_blank">Code</a>';
      }
      html += '  </div>';
      html += '</div>';
    });
    html += '</div>';

    container.innerHTML = html;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initGalleryWidgets);
  } else {
    initGalleryWidgets();
  }
})();
"""


@router.get("/embed/gallery.js")
def get_gallery_widget_js():
    """Serve standalone, zero-dependency embeddable gallery widget script."""
    return Response(
        content=EMBED_JS_CODE,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/api/v1/embed/events/{event_id}/projects")
def api_get_embed_projects(
    event_id: str,
    limit: int = Query(default=12, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Public JSON data endpoint for embeddable gallery widget (submitted projects only)."""
    event = db.query(Event).filter((Event.id == event_id) | (Event.slug == event_id)).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    projects = (
        db.query(Project)
        .filter(Project.event_id == event.id, Project.is_submitted.is_(True))
        .order_by(Project.submitted_at.desc())
        .limit(limit)
        .all()
    )

    data = []
    for p in projects:
        data.append({
            "id": p.id,
            "title": p.title,
            "tagline": p.tagline,
            "description": p.description[:200] if p.description else None,
            "team_name": p.team.name if p.team else None,
            "track_name": p.track.title if p.track else None,
            "demo_url": p.demo_url,
            "repository_url": p.repository_url,
            "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
        })

    return data


@router.get("/events/{slug}/embed", response_class=HTMLResponse)
def html_embed_dashboard(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Organizer embed snippet generator and live preview."""
    event = db.query(Event).filter((Event.slug == slug) | (Event.id == slug)).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")

    if current_user.role != "organizer" and event.organizer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Organizer access required.")

    base_url = str(request.base_url).rstrip("/")
    snippet = f'<div id="chameleon-gallery-widget" data-event-id="{event.id}" data-base-url="{base_url}"></div>\n<script src="{base_url}/embed/gallery.js" async></script>'

    return templates.TemplateResponse(
        request=request,
        name="embed_dashboard.html",
        context={
            "request": request,
            "settings": settings,
            "user": current_user,
            "event": event,
            "snippet": snippet,
            "base_url": base_url,
        },
    )
