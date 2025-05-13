```docker compose up --build```  
```
chmod +x /data3/amal.joseph/template_api/auto-deploy.sh
sudo systemctl daemon-reload
sudo systemctl enable auto-deploy.service


start immediately - sudo systemctl start auto-deploy.service


journalctl --user -u auto-deploy.service -e
cat /tmp/auto-deploy-debug.log

```  