from __future__ import annotations

import json
import sys
from pathlib import Path
from assistant import load_assistant


def main():
    assistant = load_assistant(Path(__file__).resolve().parent)
    session_id = 'cli'
    print('Sandbox Shipping demo. Type /quit to exit.')
    while True:
        try:
            msg = input('you> ').strip()
        except EOFError:
            break
        if msg in {'/quit', '/exit'}:
            break
        resp = assistant.process(session_id, msg, transcript_reference='cli')
        print('bot>', resp['reply'])
        if resp.get('routed_to'):
            print('route>', json.dumps(resp['routed_to']))
        if resp.get('lead_record_path'):
            print('lead>', resp['lead_record_path'])


if __name__ == '__main__':
    main()
