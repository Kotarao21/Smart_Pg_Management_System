# init_db_now.py
from app import db, User, PG, Room, Role
db.create_all()
if not User.query.filter_by(email='owner@example.com').first():
    u = User(name='Owner', email='owner@example.com', role=Role.OWNER)
    u.set_password('ownerpass')
    db.session.add(u)

if PG.query.count() == 0:
    pg = PG(name='Central PG', address='123, MG Road')
    db.session.add(pg)
    db.session.flush()
    r1 = Room(pg_id=pg.id, room_no='101', room_type='Single', total_beds=1, rent_per_bed=6000)
    r2 = Room(pg_id=pg.id, room_no='102', room_type='Double', total_beds=2, rent_per_bed=4000)
    db.session.add_all([r1, r2])
db.session.commit()
print("DB created and seeded.")

