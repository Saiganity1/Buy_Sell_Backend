from django.apps import AppConfig
import os


class MarketConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'market'

    def ready(self):
        """
        Automatically apply pending migrations on startup when AUTO_MIGRATE=1 (default).
        This is a safety net for environments (like Render) where the start command might
        have been set before adding a migrate step. For production with multiple instances
        or high concurrency, it's better to run migrations explicitly during deploy.
        Set AUTO_MIGRATE=0 to disable.
        """
        if os.getenv("AUTO_MIGRATE", "1") != "1":
            return
        try:
            from django.db import connections
            from django.db.migrations.executor import MigrationExecutor
            from django.core.management import call_command
            connection = connections['default']
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if plan:
                print("[auto-migrate] Pending migrations detected; applying...")
                call_command('migrate', interactive=False, run_syncdb=True)
                print("[auto-migrate] Migrations applied.")
            else:
                print("[auto-migrate] No pending migrations.")
        except Exception as e:
            # Non-fatal: log and continue startup.
            print(f"[auto-migrate] Skipped due to error: {e}")
