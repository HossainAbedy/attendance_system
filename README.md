# Attendance System (ZKTeco → Forwarder)

## Overview
**Role:** Developer / Integrator / Deployer  
**Technologies:** Flask, Python, MySQL (or CSV forwarding), ZKTeco SDK/APIs, Cron/Worker scripts, Threading  
**ANZSCO mapping:** 263111 (Network & Systems) + 261312 (Developer Programmer)

## Summary
Small service to fetch attendance logs from ZKTeco devices and forward them into a central DB or HR system. Built to automate manual CSV collection and reduce admin overhead.

## Responsibilities
- Implemented the device poller and log parser (Python).
- Implement scheduler
- Implement exporter 
- Built a Flask microservice with REST endpoints for manual triggering and status.  
- Created DB schema and forwarding logic for HR integration.

## How to run (dev)
1. `source ./venv/Scripts/activate`  
2. `pip install -r requirements.txt`  
3. `python app.py` or run the included Docker compose.


