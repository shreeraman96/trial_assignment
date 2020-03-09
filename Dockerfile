FROM python:3

ADD . .

RUN pip install -r requirements.txt

CMD ["bokeh", "serve" ,"--allow-websocket-origin=176.9.93.228:5006","--show", "method_2.py"]
