"""Operator-triggered, bounded reconciliation; default is a read-only preview."""

from django.core.management.base import BaseCommand, CommandError

from payments.reconciliation import reconcile


class Command(BaseCommand):
  help = 'Preview eligible DATAFAST internal IDs; --apply enables GET-only reconciliation.'

  def add_arguments(self, parser):
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--limit', type=int, default=50)
    parser.add_argument('--attempt-id', type=int, action='append', dest='attempt_ids')
    parser.add_argument('--refund-id', type=int, action='append', dest='refund_ids')

  def handle(self, *args, **options):
    try:
      rows = reconcile(
        limit=options['limit'],
        apply=options['apply'],
        attempt_ids=options['attempt_ids'],
        refund_ids=options['refund_ids'],
      )
    except ValueError as exc:
      raise CommandError(str(exc)) from None
    mode = 'apply' if options['apply'] else 'dry-run'
    settled = sum(row['reason'] == 'settled' for row in rows)
    self.stdout.write(f'{mode}: selected={len(rows)} settled={settled} unresolved={len(rows) - settled}')
    for row in rows:
      self.stdout.write(f'{row["kind"]}={row["id"]} status={row["status"]} reason={row["reason"]}')
