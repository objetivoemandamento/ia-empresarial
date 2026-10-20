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
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Escritório/i }).first()).toBeVisible();

  await page.getByRole('button', { name: /Agentes IA/i }).click();
  await expect(page.getByRole('heading', { name: 'Escritório de IAs' }).first()).toBeVisible();
  await expect(page.getByText(/quatro tarefas independentes/i)).toBeVisible();

  await page.getByRole('button', { name: /Permissões/i }).click();
  await expect(page.getByRole('heading', { name: 'Permissões' }).first()).toBeVisible();
  await expect(page.getByText(/PROTEÇÕES OBRIGATÓRIAS/i)).toBeVisible();

  await page.getByRole('button', { name: /Conexões/i }).click();
  await expect(page.getByRole('heading', { name: 'Conexões de IA' }).first()).toBeVisible();
  await page.getByLabel('ID exato do modelo').fill('test-model-id');
  await page.getByRole('button', { name: 'Adicionar modelo' }).click();
  await expect(page.getByText(/Groq · test-model-id/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Copiar configuração' })).toBeEnabled();

  await page.getByRole('button', { name: 'Escritório' }).click();
  await expect(page.getByRole('heading', { name: /Escritório/i }).first()).toBeVisible();
});
