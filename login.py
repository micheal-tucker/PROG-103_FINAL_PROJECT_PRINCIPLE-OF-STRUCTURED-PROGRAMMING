
ADMIN_USER='admin'
ADMIN_PASS='admin123'

def authenticate(user,password):
    return user==ADMIN_USER and password==ADMIN_PASS
