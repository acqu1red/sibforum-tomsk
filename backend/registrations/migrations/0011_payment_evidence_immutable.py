from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('''CREATE FUNCTION registrations_payment_evidence_immutable() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'Payment evidence is immutable'; END; $$ LANGUAGE plpgsql''')
    for table in ('registrations_paymentinstruction', 'registrations_paymentconfirmation'):
        schema_editor.execute(f'CREATE TRIGGER immutable_payment_evidence BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION registrations_payment_evidence_immutable()')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for table in ('registrations_paymentinstruction', 'registrations_paymentconfirmation'):
        schema_editor.execute(f'DROP TRIGGER immutable_payment_evidence ON {table}')
    schema_editor.execute('DROP FUNCTION registrations_payment_evidence_immutable()')


class Migration(migrations.Migration):
    dependencies = [('registrations', '0010_gate_attendance_and_manual_payments')]
    operations = [migrations.RunPython(install, uninstall)]
