"""Add all new tables: ATS, custom fields, reconciliation-supporting tables,
performance reviews, expenses, notifications, adjustments, garnishments,
leave, contractors, benefits, salary bands, bank accounts, documents, scheduler.

Revision ID: 003
Revises: 002
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    # Add manager_id to employees
    op.add_column('employees', sa.Column(
        'manager_id',
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey('employees.id', ondelete='SET NULL'),
        nullable=True
    ))

    # ── ATS ────────────────────────────────────────────────────
    op.create_table('job_postings',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE')),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('department', sa.String(100)),
        sa.Column('location', sa.String(200)),
        sa.Column('work_mode', sa.String(20), server_default='onsite'),
        sa.Column('job_type', sa.String(20), server_default='full_time'),
        sa.Column('salary_min', sa.Integer),
        sa.Column('salary_max', sa.Integer),
        sa.Column('description', sa.Text),
        sa.Column('requirements', sa.Text),
        sa.Column('benefits_summary', sa.Text),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('target_hire_date', sa.Date),
        sa.Column('headcount', sa.Integer, server_default='1'),
        sa.Column('filled_count', sa.Integer, server_default='0'),
        sa.Column('hiring_manager_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('employees.id')),
        sa.Column('posted_at', sa.DateTime(timezone=True)),
        sa.Column('closed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table('candidates',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), primary_key=True),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('job_postings.id', ondelete='CASCADE')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE')),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(30)),
        sa.Column('linkedin_url', sa.String(500)),
        sa.Column('stage', sa.String(30), server_default='applied'),
        sa.Column('rating', sa.Integer),
        sa.Column('source', sa.String(50), server_default='direct'),
        sa.Column('notes', sa.Text),
        sa.Column('tags', postgresql.JSONB, server_default='[]'),
        sa.Column('offer_amount', sa.Integer),
        sa.Column('offer_date', sa.Date),
        sa.Column('hired_date', sa.Date),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('employees.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table('hiring_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('candidates.id', ondelete='CASCADE')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE')),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('author_name', sa.String(200)),
        sa.Column('note_type', sa.String(30), server_default='general'),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('rating', sa.Integer),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Custom fields ──────────────────────────────────────────
    op.create_table('custom_field_schemas',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE')),
        sa.Column('entity_type', sa.String(30), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200), nullable=False),
        sa.Column('field_type', sa.String(30), nullable=False),
        sa.Column('options', postgresql.JSONB, server_default='[]'),
        sa.Column('required', sa.Boolean, server_default='false'),
        sa.Column('description', sa.Text),
        sa.Column('sort_order', sa.String(5), server_default='0'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('company_id', 'entity_type', 'field_name'),
    )

    op.create_table('custom_field_values',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE')),
        sa.Column('schema_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('custom_field_schemas.id', ondelete='CASCADE')),
        sa.Column('entity_type', sa.String(30), nullable=False),
        sa.Column('entity_id', sa.String(100), nullable=False),
        sa.Column('value_text', sa.Text),
        sa.Column('value_json', postgresql.JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Payroll adjustments ────────────────────────────────────
    op.create_table('payroll_adjustments',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE')),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('employees.id', ondelete='CASCADE')),
        sa.Column('adjustment_type', sa.String(50), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('is_taxable', sa.Boolean, server_default='true'),
        sa.Column('description', sa.Text),
        sa.Column('effective_date', sa.Date, nullable=False),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('pay_run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('pay_runs.id')),
        sa.Column('approved_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('applied_at', sa.DateTime(timezone=True)),
    )

    # Indexes
    op.create_index('idx_jobs_company_003', 'job_postings', ['company_id', 'status'])
    op.create_index('idx_candidates_job_003', 'candidates', ['job_id', 'stage'])
    op.create_index('idx_cfv_entity_003', 'custom_field_values', ['entity_type', 'entity_id'])
    op.create_index('idx_adj_employee_003', 'payroll_adjustments', ['employee_id', 'status'])


def downgrade():
    op.drop_table('payroll_adjustments')
    op.drop_table('custom_field_values')
    op.drop_table('custom_field_schemas')
    op.drop_table('hiring_notes')
    op.drop_table('candidates')
    op.drop_table('job_postings')
    op.drop_column('employees', 'manager_id')
