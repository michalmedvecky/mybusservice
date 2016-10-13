FROM ubuntu:16.04

RUN apt-get update && apt-get -y install python-dev python-pip git python-virtualenv
RUN mkdir /opt/mybusservice/
RUN git clone https://github.com/michalmedvecky/mybusservice.git /opt/mybusservice/
RUN virtualenv /opt/mybusservice/app
RUN /opt/mybusservice/app/bin/pip install -r /opt/mybusservice/requirements.txt

CMD /opt/mybusservice/app/bin/python /opt/mybusservice/app.py

