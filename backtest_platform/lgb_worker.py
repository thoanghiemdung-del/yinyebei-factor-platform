"""Standalone LGB worker — runs in subprocess to avoid GIL blocking Flask."""
import sys, os, json, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '模型'))

def main():
    if len(sys.argv) < 2:
        print("Usage: lgb_worker.py <task_file>", file=sys.stderr)
        sys.exit(1)
    task_file = sys.argv[1]
    result_file = task_file.replace('.json', '_result.json')

    try:
        with open(task_file, 'r', encoding='utf-8') as f:
            task = json.load(f)

        _write_status(result_file, {'status': 'running', 'progress': 5})

        from app import app as flask_app, _do_lgb_training, _to_json_safe
        data = task['data']

        _write_status(result_file, {'status': 'running', 'progress': 10})

        # Run training within Flask app context (needed for jsonify)
        with flask_app.app_context():
            rv = _do_lgb_training(data)

        # Parse result
        status_code = 200
        response = rv
        if isinstance(rv, tuple):
            response = rv[0]
            status_code = rv[1] if len(rv) > 1 else 200
        payload = response.get_json() if hasattr(response, 'get_json') else response
        if status_code >= 400 or (isinstance(payload, dict) and payload.get('error')):
            raise RuntimeError((payload or {}).get('error') if isinstance(payload, dict) else str(payload))

        _write_status(result_file, {
            'status': 'done',
            'progress': 100,
            'result': _to_json_safe(payload),
        })

    except Exception as e:
        traceback.print_exc()
        _write_status(result_file, {
            'status': 'error',
            'progress': 0,
            'error': f'LightGBM training failed: {str(e)}',
        })
    finally:
        # Clean up task file
        try:
            os.remove(task_file)
        except OSError:
            pass


def _write_status(path, data):
    data['updated_at'] = time.time()
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


if __name__ == '__main__':
    main()
