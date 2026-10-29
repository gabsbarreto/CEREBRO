from fastapi.testclient import TestClient

from app import config
from app.main import app, job_queue
from app.services import projects, text_extraction


def test_project_lifecycle_and_dashboard_visits(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(job_queue, "active_job_ids", lambda **kwargs: set())
    monkeypatch.setattr(text_extraction.text_job_queue, "active_job_ids", lambda **kwargs: set())
    client = TestClient(app)
    project = projects.create_project("Project A", "Description", "pdf_structured")
    project_id = project["project_id"]

    page = client.get("/projects")
    assert page.status_code == 200
    assert "Project A" in page.text
    assert "Not yet opened" in page.text
    assert client.get("/", follow_redirects=False).headers["location"] == "/projects"

    dashboard = client.get(project["dashboard_path"])
    assert dashboard.status_code == 200
    assert 'class="project-topnav"' in dashboard.text
    assert projects.get_project(project_id)["last_seen_at"]

    assert client.post(f"/api/projects/{project_id}/archive", data={"archived": "true"}).status_code == 200
    assert projects.get_project(project_id)["archived"] is True
    assert client.post(f"/api/projects/{project_id}/archive", data={"archived": "false"}).status_code == 200
    assert projects.get_project(project_id)["archived"] is False

    marker = projects.project_root(project_id) / "jobs" / "example.txt"
    marker.write_text("project data", encoding="utf-8")
    monkeypatch.setattr(job_queue, "active_job_ids", lambda **kwargs: {"job-in-progress"})
    assert client.delete(f"/api/projects/{project_id}").status_code == 409
    assert marker.exists()

    monkeypatch.setattr(job_queue, "active_job_ids", lambda **kwargs: set())
    assert client.delete(f"/api/projects/{project_id}").status_code == 200
    assert not projects.project_root(project_id).exists()
    assert client.delete("/api/projects/legacy-jobs").status_code == 400
