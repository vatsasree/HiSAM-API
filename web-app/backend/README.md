[TODO]

[ --- EASY --- ] 
[TODO] add log to jobs even if file error is there. and add reason
[TODO] Process PDF in chunks, before saving it to disk.
[TODO] Handle when a job fails before adding to db  - eg: wrong file type, we should still add them to the db and mention, this happened and job failed.



[ --- HARD --- ]
[TODO] estimated processing time - based on size, estimated completion time from api
[TODO] Dockerize Everything.


<!-- [ --- CRITICAL --- ] -->
<!-- [TODO] check out of memory error?
[TODO] Check Gateway 504 timeout error. -->


[DATABASE CHANGES]
[TODO] Add job_id as numeric and job_uuid
[TODO] image save path in store should be uuid, and the path for user seperate in db


[!!!! IMPORTANT]
[TODO] Document update status as fails if there are no lines detected.
[TODO] Make the web-app dockerized
[TODO] Health check of celery and webapp - restart if down.
[TODO] Rescale the heatmap if needed.


curl -X GET "https://skeleton.iiit.ac.in/api/v1/polylines/status/fa4965c8-eee8-4a93-919d-4b9da6ddb4a1" \
     -H "accept: application/json" \
     -H "X-API-Token: usk_mEcOT4EAFyYWagbQIRvYBfqfamkDAyzW_utc9OHWYg27rpVSQQtz8A"


# Alembic Migrations
```
alembic revision --autogenerate -m "Privilage tables added"
alembic upgrade head
```

changes to api docs and scripts - check notepad


# Different Logs
/data3/amal.joseph/template_api/store/log_files/parsing_records.log
/data3/amal.joseph/template_api/store/log_files/celery_log.log