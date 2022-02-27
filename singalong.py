from functools import lru_cache

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
    def default(self, project):
        try:
            token = cherrypy.session["token"]
        except KeyError:
            cherrypy.session["project"] = project
            raise cherrypy.HTTPRedirect("authenticate")
        try:
            return read_html_for_project(project=project, group=self.group, token=token)
        except UnknownProject:
            return f"WTF is {project} !!!"
        except InvalidToken:
            del cherrypy.session["token"]
            return "WTF are you !!! <a href='https://gitlab.com/-/profile/personal_access_tokens' target='_blank'>get a token</a>."

    @cherrypy.expose
    def authenticate(self, project=None, token=None):
        if token is not None:
            cherrypy.session["token"] = token
            raise cherrypy.HTTPRedirect(project)
        return f"""<html>
          <head></head>
          <body>
            <form method="POST" action="authenticate">
              <input type="text" value="" name="token" />
              <input type="hidden" value="{cherrypy.session["project"]}" name="project" />
              <button type="submit">authenticate</button>
            </form>
          </body>
        </html>"""


@lru_cache()
def get_group_id(*, group, token):
    """
    >>> get_group_id(group="PNCKS", token="glpat-4vFiVNbFsqAVDesBYRGV")
    14660398
    """
    response = httpx.get(
        f"{API}/groups?search={group}", headers={"PRIVATE-TOKEN": token}
    )
    return response.json()[0]["id"]


@lru_cache()
def get_project_id(*, project, group, token):
    """
    >>> get_project_id(project="healthcheck", group="PNCKS", token="glpat-4vFiVNbFsqAVDesBYRGV")
    33978260
    """
    group_id = get_group_id(group=group, token=token)
    response = httpx.get(
        f"{API}/groups/{group_id}/projects/", headers={"PRIVATE-TOKEN": token}
    )
    if response.status_code == 401:  # unauthorized
        raise InvalidToken(token)
    for project_dict in response.json():
        if project_dict["name"] == project:
            return project_dict["id"]
    else:
        raise UnknownProject(project)


class InvalidToken(Exception):
    pass


class UnknownProject(Exception):
    pass


def read_html_for_project(*, project, group, token):
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
        f"{API}/projects/{get_project_id(project=project, group=group, token=token)}/repository/files/{project}.html/raw",
        headers={"PRIVATE-TOKEN": token},
    )
    if response.status_code == 404:
        return f"WTF ... {project}.html does not exist mate!"
    return response.text


if __name__ == "__main__":
    main()
