
#!/bin/bash
cd "$(dirname "$0")"
echo "Starting BierStrava on http://localhost:5001 ..."
sleep 1 && open http://localhost:5001 &
python3 run.py
