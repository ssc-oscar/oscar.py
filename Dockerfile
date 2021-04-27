FROM gcc
FROM python:3

#RUN apt update && apt -y install python-pip libtokyocabinet-dev
RUN apt update && apt install -y libtokyocabinet-dev

WORKDIR /home/python

COPY oscar.pyx  oscar.pyxbld requirements.txt setup.py tests/ docs/ Makefile  ./

RUN pip install --no-cache-dir -r requirements.txt
