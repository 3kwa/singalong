FROM --platform=linux/amd64 python:3.10-slim
COPY *.py ./
RUN pip install cherrypy click httpx
ENTRYPOINT ["python",  "-m", "singalong"]

