import os
BASE = os.path.dirname(os.path.abspath(__file__))
h=open(os.path.join(BASE, 'templates', 'dashboard_v2.html'), 'r', encoding='utf-8').read()
h=h.replace('/dashboard_v2','/dashboard')
open(os.path.join(BASE, 'templates', 'dashboard.html'), 'w', encoding='utf-8').write(h)
print('dashboard = working v2')
