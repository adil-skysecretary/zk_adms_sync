{
    'name': 'ZK ADMS Attendance Sync',
    'version': '18.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Receive ADMS attendance push logs from biometric devices',
    'depends': ['base', 'hr_attendance'],
    'data': [
        'views/hr_employee_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}