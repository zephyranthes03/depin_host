docker run --name redis -p 6379:6379 -v /your/local/path:/data -d redis redis-server --appendonly yes
