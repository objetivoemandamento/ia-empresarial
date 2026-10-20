import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      ok: true, language_default: 'pt', supported_languages: ['pt', 'en', 'zh', 'es', 'hi'],
      llm_ready: true, llm_mode: 'configured', llm_model: 'test-model', transcription_ready: false,
    }),
  }));
  await page.route('**/api/repositories', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ skills: [] }),
  }));
  await page.route('**/api/policies', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      voice_enabled: true, approved_skills_enabled: true, prime_sandbox_enabled: false,
      external_network_enabled: false, optional_telemetry_enabled: true,
      protected_controls: [
        { key: 'financial_actions', title: 'Transferências, pagamentos e saques bloqueados', enabled: true },
        { key: 'authentication', title: 'Autenticação obrigatória', enabled: true },
        { key: 'security_audit', title: 'Auditoria de segurança obrigatória', enabled: true },
      ],
    }),
  }));
});

test('workspace preserves home and exposes AI office, permissions, and connections tabs', async ({ page }) => {
  const project = test.info().project.name;
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Escritório/i }).first()).toBeVisible();

  await page.getByRole('button', { name: /Agentes IA/i }).click();
  await expect(page.getByRole('heading', { name: 'Escritório de IAs' }).first()).toBeVisible();
  await expect(page.getByText(/quatro tarefas independentes/i)).toBeVisible();
  await page.screenshot({ path: `test-results/${project}-office.png`, fullPage: true });

  await page.getByRole('button', { name: /Permissões/i }).click();
  await expect(page.getByRole('heading', { name: 'Permissões' }).first()).toBeVisible();
  await expect(page.getByText('PROTEÇÕES OBRIGATÓRIAS', { exact: true })).toBeVisible();
  await page.screenshot({ path: `test-results/${project}-permissions.png`, fullPage: true });

  await page.getByRole('button', { name: /Conexões/i }).click();
  await expect(page.getByRole('heading', { name: 'Conexões de IA' }).first()).toBeVisible();
  await page.getByLabel('ID exato do modelo').fill('test-model-id');
  for (const task of ['general', 'research', 'marketing', 'analysis']) {
    await page.getByLabel(task, { exact: true }).uncheck();
  }
  await expect(page.getByLabel('coding', { exact: true })).toBeChecked();
  await page.getByRole('button', { name: 'Adicionar modelo' }).click();
  await expect(page.getByText(/Groq · test-model-id/)).toBeVisible();
  await page.getByText('Ver configuração para copiar manualmente').click();
  await expect(page.getByText(/"tasks":\["coding"\]/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Copiar configuração' })).toBeEnabled();
  await page.screenshot({ path: `test-results/${project}-connections.png`, fullPage: true });

  await page.getByRole('button', { name: 'Escritório' }).click();
  await page.getByRole('button', { name: /Conexões/i }).click();
  await expect(page.getByText(/Groq · test-model-id/)).toBeVisible();

  await page.getByRole('button', { name: 'Escritório' }).click();
  await expect(page.getByRole('heading', { name: /Escritório/i }).first()).toBeVisible();
  await page.screenshot({ path: `test-results/${project}-home.png`, fullPage: true });
});

test('admin can inspect a persisted agent run and its audit timeline', async ({ page }) => {
  await page.route('**/api/human-tasks', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ tasks: [] }),
  }));
  await page.route('**/api/agent-runs', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ runs: [{ id: 1, goal: 'Revisar uma proposta', status: 'delivered', error: null, created: 1, updated: 2 }] }),
  }));
  await page.route('**/api/agent-runs/1', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      id: 1, goal: 'Revisar uma proposta', status: 'delivered', result: 'Proposta revisada',
      error: null, tasks: [{ id: 2, idx: 0, title: 'Revisar proposta', specialist: 'Qualidade',
        instructions: 'Revisar', action: null, status: 'done', output: 'Revisão concluída',
        review: 'Aprovado', attempts: 1, error: null }],
      approvals: [], events: [
        { id: 1, run_id: 1, ts: 1781900000, kind: 'run.created', detail: 'Objetivo registrado' },
        { id: 2, run_id: 1, ts: 1781900001, kind: 'run.delivered', detail: 'Entrega concluída' },
      ],
    }),
  }));
  await page.goto('/');
  await page.getByLabel('Token administrativo').fill('test-admin-token');
  await page.getByRole('button', { name: /Agentes IA/i }).click();
  await expect(page.getByText(/#1 · Entregue/)).toBeVisible();
  await page.getByRole('button', { name: 'Detalhes' }).click();
  await expect(page.getByText(/Histórico de auditoria \(2 eventos\)/)).toBeVisible();
  await page.getByText(/Histórico de auditoria \(2 eventos\)/).click();
  await expect(page.getByText('run.delivered', { exact: true })).toBeVisible();
  await expect(page.getByText('Qualidade · Concluída · tentativas 1')).toBeVisible();
});

