from apscheduler.schedulers.background import BackgroundScheduler
from seed import schedule

def start():
    sched = BackgroundScheduler()
    sched.add_job(schedule, trigger="date")
    sched.start()
