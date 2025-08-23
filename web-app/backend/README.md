[TODO]

[ --- EASY --- ] 
[TODO] add log to jobs even if file error is there. and add reason
[TODO] Process PDF in chunks, before saving it to disk.
[TODO] Handle when a job fails before adding to db  - eg: wrong file type, we should still add them to the db and mention, this happened and job failed.



[ --- HARD --- ]
[TODO] estimated processing time - based on size, estimated completion time from api
[TODO] Dockerize Everything.



[DATABASE CHANGES]
[TODO] Add job_id as numeric and job_uuid as seperate
[TODO] image save path in store should be uuid, and the path for user seperate in db


[!!!! IMPORTANT]
[TODO] Make the web-app dockerized
[TODO] Health check of celery and webapp - restart if down.
[TODO] Rescale the heatmap if needed.




# Alembic Migrations
```
alembic revision --autogenerate -m "Privilage tables added"
alembic upgrade head
```

changes to api docs and scripts - check notepad


# Different Logs
/data3/amal.joseph/template_api/store/log_files/parsing_records.log
/data3/amal.joseph/template_api/store/log_files/celery_log.log