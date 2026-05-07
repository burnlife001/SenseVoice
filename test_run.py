import sys
sys.stdout.reconfigure(line_buffering=True)
from voice_input_client import VoiceInputApp
print('Creating app...', flush=True)
app = VoiceInputApp()
print('App created', flush=True)
print('Starting run...', flush=True)
app.run()
