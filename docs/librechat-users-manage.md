login using ssh, then

GET USERS:

docker compose -f docker-compose.yml exec mongodb mongosh LibreChat --quiet --eval \
  'db.users.find({}, {_id:0, email:1}).forEach(u => print(u.email))'

DELETE USER:

docker compose -f docker-compose.yml exec mongodb mongosh LibreChat --quiet --eval \
  'db.users.deleteOne({email: "user@example.com"})'