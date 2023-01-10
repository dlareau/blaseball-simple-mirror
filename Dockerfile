FROM python:3

EXPOSE 5000

WORKDIR /app

COPY . ./

RUN pip install -r requirements.txt

CMD ["python", "mirror.py"]
