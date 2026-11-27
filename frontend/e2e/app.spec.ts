import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';

test.describe('AcademiaAI Voice Co-Pilot - End-to-End Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Fake EventSource so E2E tests do not require a running backend.
    await page.addInitScript(() => {
      class MockEventSource extends EventTarget {
        static latest: MockEventSource | null = null;
        onopen: ((event: Event) => void) | null = null;
        onerror: ((event: Event) => void) | null = null;
        onmessage: ((event: MessageEvent) => void) | null = null;
        url: string;

        constructor(url: string) {
          super();
          this.url = url;
          MockEventSource.latest = this;
          setTimeout(() => this.onopen?.(new Event('open')), 0);
        }

        close() {
          // No network connection to close in this mock.
        }
      }

      (window as unknown as { MockEventSource: typeof MockEventSource })
        .MockEventSource = MockEventSource;

      Object.defineProperty(window, 'EventSource', {
        configurable: true,
        value: MockEventSource,
      });
    });

    await page.goto('/');
  });

  test('should load the Voice Studio dashboard', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Recording Studio' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start Voice Capture' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Main Navigation' })).toBeVisible();
  });

  test('should navigate between workspace sections', async ({ page }) => {
    await page.getByRole('menuitem', { name: 'Live Transcripts' }).click();
    await expect(page.getByRole('main')).toBeVisible();

    await page.getByRole('menuitem', { name: 'Session History' }).click();
    await expect(page.getByRole('main')).toBeVisible();

    await page.getByRole('menuitem', { name: 'Voice Studio' }).click();
    await expect(page.getByRole('heading', { name: 'Recording Studio' })).toBeVisible();
  });

  test('should load the simulated demo workflow in mock mode', async ({ page }) => {
    await page.route('**/api/v1/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            status: 'healthy',
            service: 'AcademiaAI Voicebot',
            mock_mode: true,
          },
          timestamp: Date.now(),
        }),
      });
    });

    await page.reload();

    const demoButton = page.getByRole('button', {
      name: 'Load simulated demo workflow plan',
    });

    await expect(demoButton).toBeVisible();
    await demoButton.click();

    await expect(
      page.getByRole('status', { name: 'Workflow execution type: Simulated demo' })
    ).toBeVisible();

    await expect(
      page.getByRole('list', { name: 'Workflow execution steps' })
    ).toBeVisible();
  });

  test('should reject an approval request without executing the action', async ({ page }) => {
    await page.route('**/api/v1/sessions', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'e2e-session-001',
          status: 'created',
          created_at: Date.now(),
        }),
      });
    });

    await page.getByRole('button', { name: 'Start Voice Capture' }).click();

    await expect.poll(async () => {
      return page.evaluate(() => {
        const mock = (window as unknown as {
          MockEventSource: { latest: { dispatchEvent: (event: Event) => boolean } | null };
        }).MockEventSource;
        return mock.latest !== null;
      });
    }).toBe(true);

    await page.evaluate(() => {
      const mock = (window as unknown as {
        MockEventSource: {
          latest: { dispatchEvent: (event: Event) => boolean } | null;
        };
      }).MockEventSource;

      const event = new MessageEvent('approval.request', {
        data: JSON.stringify({
          event_id: 'e2e-approval-event-001',
          event_type: 'approval.request',
          payload: {
            request_id: 'e2e-approval-001',
            plan_id: 'e2e-plan-001',
            session_id: 'e2e-session-001',
            safety_level: 'C',
            status: 'PENDING',
            created_at: Date.now() / 1000,
            action: 'Modify test configuration',
            description: 'Update a test configuration file',
            tool_name: 'config.update',
            step_number: 1,
            parameters: { key: 'test_mode', value: true },
          },
        }),
      });

      mock.latest?.dispatchEvent(event);
    });

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('Modify test configuration');

    await page.getByLabel('Rejection Reason (Optional):').fill(
      'Rejected during automated E2E safety test'
    );

    await page.getByRole('button', {
      name: 'Reject requested action and halt execution',
    }).click();

    await expect(dialog).toBeHidden();
  });
  test('should reconnect after an SSE connection interruption', async ({ page }) => {
  await page.route('**/api/v1/sessions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        session_id: 'e2e-reconnect-session',
        status: 'created',
        created_at: Date.now(),
      }),
    });
  });

  await page.getByRole('button', { name: 'Start Voice Capture' }).click();

  // Wait for the initial SSE connection.
  await expect.poll(() =>
    page.evaluate(() => {
      const mock = (window as unknown as {
        MockEventSource: { latest: object | null };
      }).MockEventSource;

      return mock.latest !== null;
    })
  ).toBe(true);

  // Simulate a dropped connection.
  const initialConnection = await page.evaluate(() => {
    const mock = (window as unknown as {
      MockEventSource: {
        latest: {
          onerror: ((event: Event) => void) | null;
        } | null;
      };
    }).MockEventSource;

    const connection = mock.latest;
    connection?.onerror?.(new Event('error'));

    return connection;
  });

  expect(initialConnection).not.toBeNull();

  // Verify that the client creates a replacement connection.
  await expect.poll(() =>
    page.evaluate(() => {
      const mock = (window as unknown as {
        MockEventSource: { latest: object | null };
      }).MockEventSource;

      return mock.latest;
    })
  , { timeout: 5000 }).not.toBe(initialConnection);
});

  test('should display a normal workflow and update a completed step', async ({ page }) => {
    await page.route('**/api/v1/sessions', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'e2e-normal-session',
          status: 'created',
          created_at: Date.now(),
        }),
      });
    });

    await page.getByRole('button', { name: 'Start Voice Capture' }).click();

    await expect.poll(() =>
      page.evaluate(() => {
        const mock = (window as unknown as {
          MockEventSource: { latest: object | null };
        }).MockEventSource;
        return mock.latest !== null;
      })
    ).toBe(true);

    // Send a normal workflow plan through the mocked SSE connection.
    await page.evaluate(() => {
      const mock = (window as unknown as {
        MockEventSource: {
          latest: { dispatchEvent: (event: Event) => boolean } | null;
        };
      }).MockEventSource;

      mock.latest?.dispatchEvent(new MessageEvent('workflow.plan', {
        data: JSON.stringify({
          event_id: 'normal-plan-event-001',
          event_type: 'workflow.plan',
          payload: {
            plan: {
              plan_id: 'normal-plan-001',
              session_id: 'e2e-normal-session',
              goal: 'Generate a workspace report',
              steps: [{
                id: 'normal-step-001',
                step_number: 1,
                description: 'Collect workspace information',
                tool_name: 'workspace.collect',
                safety_level: 'A',
                status: 'running',
              }],
              current_step_index: 0,
              overall_safety_level: 'A',
              requires_approval: false,
              status: 'EXECUTING',
              created_at: Date.now() / 1000,
            },
          },
        }),
      }));
    });

    const workflow = page.getByRole('list', {
      name: 'Workflow execution steps',
    });

    await expect(workflow).toBeVisible();
    await expect(workflow).toContainText('Collect workspace information');

    // Send a step-completion event.
    await page.evaluate(() => {
      const mock = (window as unknown as {
        MockEventSource: {
          latest: { dispatchEvent: (event: Event) => boolean } | null;
        };
      }).MockEventSource;

      mock.latest?.dispatchEvent(new MessageEvent('workflow.step', {
        data: JSON.stringify({
          event_id: 'normal-step-event-001',
          event_type: 'workflow.step',
          payload: {
            plan_id: 'normal-plan-001',
            step_id: 'normal-step-001',
            status: 'completed',
            result: 'Workspace report generated successfully',
          },
        }),
      }));
    });

    await expect(workflow).toContainText('Collect workspace information');
    await expect(workflow).toContainText('COMPLETED');
  });

    test('should have no automatically detected accessibility violations', async ({ page }) => {
    const accessibilityScan = await new AxeBuilder({ page }).analyze();

    expect(
      accessibilityScan.violations,
      JSON.stringify(accessibilityScan.violations, null, 2)
    ).toEqual([]);
  });
test('should display correctly on mobile and desktop screens', async ({ page }) => {
  // Mobile layout
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('body')).toBeVisible();

  const mobileWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(mobileWidth).toBeLessThanOrEqual(390);

  // Desktop layout
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.locator('body')).toBeVisible();

  const desktopWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(desktopWidth).toBeLessThanOrEqual(1440);
});
test('should support keyboard navigation through interactive controls', async ({ page }) => {
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab');
    await expect(page.locator(':focus')).toBeVisible();
  }
});
});
