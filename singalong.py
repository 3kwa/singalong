from functools import lru_cache
from urllib.parse import quote_plus

import cherrypy
import click
import httpx

API = "https://gitlab.com/api/v4"


@click.command()
@click.argument("group")
@click.option("--development", is_flag=True, help="environment not production ...")
def main(group, development):
    """Serves HTML pages from gitlab.

    GROUP is the ID of the group, the projects singalong could serve belongs too.

        $ python -m singalong PNCKS
    """
    conf = {
        "/": {"tools.sessions.on": True},
        "global": {"environment": "production", "server.socket_host": "0.0.0.0"},
    }
    if development:
        del conf["global"]["environment"]
    cherrypy.quickstart(Singalong(group), "/", conf)


class Singalong:
    def __init__(self, group):
        self.group = group

    @cherrypy.expose
    def index(self):
        return "OK"

    @cherrypy.expose
    def default(self, project, *crumbs):
        if crumbs:
            path = "/".join(crumbs)
        else:
            path = project
        try:
            token = cherrypy.session["token"]
        except KeyError:
            cherrypy.session["project"] = project
            cherrypy.session["path"] = path
            raise cherrypy.HTTPRedirect("/authenticate")
        try:
            return read_html_for_project(path=path, project=project, group=self.group, token=token)
        except UnknownGroup:
            return f"WTF is your sysadmin doing! WTF is {self.group}!"
        except UnknownProject:
            return f"WTF is {project} !!!"
        except InvalidToken:
            del cherrypy.session["token"]
            return "WTF are you !!! <a href='https://gitlab.com/-/profile/personal_access_tokens' target='_blank'>get a token</a>."

    @cherrypy.expose
    def authenticate(self, path=None, project=None, token=None):
        if token is not None:
            cherrypy.session["token"] = token
            raise cherrypy.HTTPRedirect(f"{project}/{path}")
        return f"""<html>
          <head>
          <style>
          html, body {{
              margin: 0;
              padding: 0;
          }}
          form {{
              background-color: lightseagreen;
          }}
          table {{
              width: 100%;
          }}
          input, button {{
            width: 100%;
          }}
          </style>
          </head>
          <body>
            <form method="POST" action="/authenticate">
              <table>
              <tr><td width="90%">
              <input type="password" value="" name="token" />
              </td><td>
              <button type="submit">authenticate</button>
              </tr></table>
              <input type="hidden" value="{cherrypy.session["project"]}" name="project" />
              <input type="hidden" value="{cherrypy.session["path"]}" name="path" />
            </form>
          </body>
        </html>"""


@lru_cache()
def get_group_id(*, group, token):
    """
    >>> get_group_id(group="PNCKS", token="glpat-4vFiVNbFsqAVDesBYRGV")
    14660398
    """
    response = httpx.get(f"{API}/groups?search={group}", headers={"PRIVATE-TOKEN": token})
    if response.status_code == 401:
        raise InvalidToken(token)
    try:
        return response.json()[0]["id"]
    except KeyError:
        raise UnknownGroup(group)


@lru_cache()
def get_project_id(*, project, group, token):
    """
    >>> get_project_id(project="healthcheck", group="PNCKS", token="glpat-4vFiVNbFsqAVDesBYRGV")
    33978260
    """
    projects = list_all_projects(group=group, token=token)
    if project not in projects:
        raise UnknownProject(project)
    return projects[project]


def list_all_projects(*, group, token):
    projects = {}
    group_id = get_group_id(group=group, token=token)
    url = f"{API}/groups/{group_id}/projects/"
    while url:
        response = httpx.get(url, headers={"PRIVATE-TOKEN": token})
        if response.status_code == 401:
            raise InvalidToken(token)
        for project in response.json():
            projects[project["name"]] = project["id"]
        # handling pagination
        link = response.headers["link"]
        for link_rel in link.split(","):
            if 'rel="next"' in link_rel:
                url = link_rel.split(";")[0][1:-1]
                break
        else:
            url = None
    return projects


class InvalidToken(Exception):
    pass


class UnknownProject(Exception):
    pass


class UnknownGroup(Exception):
    pass


def read_html_for_project(*, path, project, group, token):
    """
    >>> print(read_html_for_project(project="healthcheck", group="PNCKS", token="glpat-4vFiVNbFsqAVDesBYRGV")) #doctest: +ELLIPSIS
    <!DOCTYPE HTML>
    <html lang="en">
    <head>
    <title>healthcheck</title>
    ...

    >>> print(read_html_for_project(project="limit_up", group="PNCKS", token="glpat-4vFiVNbFsqAVDesBYRGV"))
    WTF ... limit_up.html does not exist mate!
    """
    # https://docs.gitlab.com/ee/api/repository_files.html#get-raw-file-from-repository
    response = httpx.get(
        f"{API}/projects/{get_project_id(project=project, group=group, token=token)}/repository/files/{quote_plus(path)}.html/raw",
        headers={"PRIVATE-TOKEN": token},
    )
    if response.status_code == 404:
        return f"WTF ... {project}.html does not exist mate!"
    elif response.status_code == 401:
        return f"WTF {token} got nuked!"
    return response.text


if __name__ == "__main__":
    main()
