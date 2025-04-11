overlay the output of polygons on image - when multiple images are running and sanity check
remove scribbbles
documentation website
tei format

https://celery.school/celery-worker-pools


readthedocs

User should be able to give : jpg/png/pdf as image formats
User should be able to give single or list of files as input

 
A Python script which users can run: calling the endpoint (where results are to be stored)
A Python script which users can run: checking status of job


A Python script which takes a list of inputs and results (TEI): overlays polygons
A Python script which takes a list of inputs and results (TEI): extracts each line as a sub-image 



# Alembic Migrations
```
alembic revision --autogenerate -m "documents.output changed to LONGTEXT"
alembic upgrade head
```



