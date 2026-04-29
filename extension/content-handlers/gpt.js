/**
 * GPT Image Generation Handler
 *
 * This handler implements the GPT image generation workflow:
 * 1. Find the composer textarea
 * 2. Upload reference images (if any)
 * 3. Write the prompt text
 * 4. Submit the prompt
 * 5. Wait for generated images
 * 6. Serialize and report results
 */

export async function runGptJob(job, serverUrl) {
  const logs = [];

  const record = async (message, details = null) => {
    const at = new Date().toISOString();
    const entry = { at, message };
    if (details !== null && details !== undefined) {
      entry.details = details;
    }
    logs.push(entry);
    await notifyProgress(message);
    await sendProgress(serverUrl, message, at, details);
  };

  try {
    await record(`Preparing ${job.id}`);
    const composer = await waitFor(() => findComposer(), { timeoutMs: 120000, label: "prompt composer" });

    await record("Uploading reference images");
    await uploadAssets(job);

    await record("Writing prompt");
    setComposerText(composer, job.prompt);
    await delay(500);

    const baselineAssistantCount = getAssistantTurnElements().length;
    const baselineAssistantImageKeys = collectAllAssistantImageKeys();
    const baselinePageImageKeys = collectImageKeys(getImageSearchRoot());

    await record("Submitting job", {
      composerPath: getElementPath(composer),
      visibleButtons: collectVisibleButtons(),
    });

    const submitResult = await submitPrompt(composer, baselineAssistantCount);
    await record("Submit triggered", submitResult);
    if (!submitResult.submitted) {
      throw new Error("Prompt did not submit");
    }

    await record("Waiting for generated images");
    let responseCapture = null;
    try {
      responseCapture = await waitForAssistantResponseImages(
        baselineAssistantImageKeys,
        job.timeoutSeconds ? job.timeoutSeconds * 1000 : DEFAULT_TIMEOUT_MS
      );
    } catch (_error) {
      responseCapture = await waitForGeneratedImagesAnywhere(
        baselinePageImageKeys,
        job.timeoutSeconds ? job.timeoutSeconds * 1000 : DEFAULT_TIMEOUT_MS
      );
      await record("Assistant-scope detection missed images; used page-wide fallback", {
        imageCount: responseCapture.images.length,
      });
    }

    await record(`Found ${responseCapture.images.length} generated image(s)`, {
      assistantTurn: responseCapture.assistantTurn,
    });

    const serializedImages = await serializeImages(responseCapture.images);
    await record("Saving results to local bridge", {
      imageCount: serializedImages.length,
    });

    await postJson(`${serverUrl}/v1/job/${encodeURIComponent(job.id)}/result`, {
      images: serializedImages,
      logs,
    });

    controllerState.lastError = null;
    controllerState.lastMessage = `Completed ${job.id}`;
    await chrome.runtime.sendMessage({ type: "content:finished", jobId: job.id, state: { ...controllerState } });
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    logs.push({ at: new Date().toISOString(), message: `Failed: ${reason}` });
    try {
      await postJson(`${serverUrl}/v1/job/${encodeURIComponent(job.id)}/fail`, {
        reason,
        logs,
      });
    } catch (_postError) {
      // Ignore reporting errors.
    }
    controllerState.lastError = reason;
    controllerState.lastMessage = `Failed ${job.id}`;
    await chrome.runtime.sendMessage({ type: "content:failed", jobId: job.id, reason, state: { ...controllerState } });
  }
}
