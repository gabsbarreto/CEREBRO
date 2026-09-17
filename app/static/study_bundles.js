(() => {
  "use strict";

  const SUPPORTED_ATTACHMENT_EXTENSIONS = new Set([".pdf", ".xlsx", ".csv"]);
  const SUPPLEMENTARY_NAME_PATTERN = /\b(supplement(?:ary)?|supporting(?:[ _-]+information)?|appendi(?:x|ces)|additional[ _-]+file)\b/gi;
  const SUPPLEMENTARY_NAME_TEST_PATTERN = /\b(supplement(?:ary)?|supporting(?:[ _-]+information)?|appendi(?:x|ces)|additional[ _-]+file)\b/i;

  function mountStudyBundlePicker(options) {
    const primaryInput = options.primaryInput;
    const supportingInput = options.supportingInput;
    const folderInput = options.folderInput;
    const primarySummary = options.primarySummary;
    const supportingSummary = options.supportingSummary;
    const folderSummary = options.folderSummary;
    const review = options.review;
    const reviewSummary = options.reviewSummary;
    const reviewList = options.reviewList;
    const assignments = new Map();

    const refresh = () => {
      const selection = collectSelection();
      const primaryKeys = new Set(selection.primaryFiles.map(fileKey));
      for (const [attachmentKey, primaryKey] of assignments.entries()) {
        if (!primaryKeys.has(primaryKey) || !selection.attachments.some((item) => item.key === attachmentKey)) {
          assignments.delete(attachmentKey);
        }
      }
      for (const attachment of selection.attachments) {
        if (assignments.has(attachment.key)) continue;
        const matches = selection.primaryFiles.filter((primary) => normalizedStudyStem(primary.name) === normalizedStudyStem(attachment.file.name));
        if (matches.length === 1) assignments.set(attachment.key, fileKey(matches[0]));
      }
      renderSummaries(selection);
      renderReview(selection);
      return selection;
    };

    const collectSelection = () => {
      const primaryByKey = new Map();
      const attachmentByKey = new Map();
      addPrimaryFiles(primaryByKey, fileList(primaryInput));
      for (const file of fileList(folderInput)) {
        if (!isSupportedSource(file)) continue;
        if (isPdf(file) && !looksSupplementary(file.name)) {
          addFile(primaryByKey, file);
        } else {
          addFile(attachmentByKey, file);
        }
      }
      addSupportingFiles(attachmentByKey, fileList(supportingInput));
      for (const key of primaryByKey.keys()) attachmentByKey.delete(key);
      return {
        primaryFiles: [...primaryByKey.values()],
        attachments: [...attachmentByKey.values()].map((file) => ({ file, key: fileKey(file) })),
      };
    };

    const getBundles = () => {
      const selection = refresh();
      if (!selection.primaryFiles.length) {
        return { bundles: [], error: "Choose one or more primary PDF files." };
      }
      const primaryByKey = new Map(selection.primaryFiles.map((file) => [fileKey(file), file]));
      const unassigned = selection.attachments.filter((attachment) => !primaryByKey.has(assignments.get(attachment.key)));
      if (unassigned.length) {
        const names = unassigned.slice(0, 3).map((attachment) => displayName(attachment.file));
        const suffix = unassigned.length > names.length ? ` and ${unassigned.length - names.length} more` : "";
        return { bundles: [], error: `Assign every supporting file before queueing: ${names.join(", ")}${suffix}.` };
      }
      const bundles = selection.primaryFiles.map((primary) => ({
        primary,
        attachments: selection.attachments
          .filter((attachment) => assignments.get(attachment.key) === fileKey(primary))
          .map((attachment) => attachment.file),
      }));
      return { bundles, error: "" };
    };

    const appendBundlesToFormData = (body, bundles) => {
      bundles.forEach((bundle, primaryIndex) => {
        body.append("pdfs", bundle.primary, bundle.primary.name);
        body.append("pdf_relative_paths", relativePath(bundle.primary));
        bundle.attachments.forEach((attachment) => {
          body.append("attachments", attachment, attachment.name);
          body.append("attachment_primary_indices", String(primaryIndex));
          body.append("attachment_relative_paths", relativePath(attachment));
        });
      });
      return body;
    };

    const clear = () => {
      if (primaryInput) primaryInput.value = "";
      if (supportingInput) supportingInput.value = "";
      if (folderInput) folderInput.value = "";
      assignments.clear();
      refresh();
    };

    const renderSummaries = (selection) => {
      if (primarySummary) primarySummary.textContent = primaryInputSummary(fileList(primaryInput));
      if (supportingSummary) supportingSummary.textContent = supportingInputSummary(fileList(supportingInput));
      if (folderSummary) folderSummary.textContent = folderInputSummary(fileList(folderInput));
      if (reviewSummary) {
        const bundleCount = selection.primaryFiles.length;
        const attachmentCount = selection.attachments.length;
        reviewSummary.textContent = bundleCount
          ? `${bundleCount} study ${plural(bundleCount, "bundle")} with ${attachmentCount} supporting ${plural(attachmentCount, "file")}.`
          : "Choose primary PDFs, then assign any supporting files.";
      }
    };

    const renderReview = (selection) => {
      if (!review || !reviewList) return;
      reviewList.replaceChildren();
      const hasSources = selection.primaryFiles.length || selection.attachments.length;
      review.classList.toggle("hidden", !hasSources);
      if (!hasSources) return;

      const primaryByKey = new Map(selection.primaryFiles.map((file) => [fileKey(file), file]));
      for (const primary of selection.primaryFiles) {
        const card = document.createElement("div");
        card.className = "study-bundle-card";
        const heading = document.createElement("div");
        heading.className = "study-bundle-primary";
        const title = document.createElement("strong");
        title.textContent = displayName(primary);
        const label = document.createElement("small");
        label.textContent = "Primary PDF";
        heading.append(title, label);
        card.append(heading);

        const assigned = selection.attachments.filter((attachment) => assignments.get(attachment.key) === fileKey(primary));
        if (!assigned.length) {
          const empty = document.createElement("p");
          empty.className = "study-bundle-empty";
          empty.textContent = "No supporting files attached.";
          card.append(empty);
        } else {
          const files = document.createElement("div");
          files.className = "study-bundle-files";
          assigned.forEach((attachment) => files.append(createAttachmentRow(attachment, selection.primaryFiles)));
          card.append(files);
        }
        reviewList.append(card);
      }

      const unassigned = selection.attachments.filter((attachment) => !primaryByKey.has(assignments.get(attachment.key)));
      if (unassigned.length) {
        const card = document.createElement("div");
        card.className = "study-bundle-card study-bundle-unassigned";
        const heading = document.createElement("div");
        heading.className = "study-bundle-primary";
        const title = document.createElement("strong");
        title.textContent = "Needs assignment";
        const label = document.createElement("small");
        label.textContent = "Choose a primary PDF for each supporting file";
        heading.append(title, label);
        card.append(heading);
        const files = document.createElement("div");
        files.className = "study-bundle-files";
        unassigned.forEach((attachment) => files.append(createAttachmentRow(attachment, selection.primaryFiles)));
        card.append(files);
        reviewList.append(card);
      }
    };

    const createAttachmentRow = (attachment, primaryFiles) => {
      const row = document.createElement("label");
      row.className = "study-bundle-file";
      const name = document.createElement("span");
      name.textContent = displayName(attachment.file);
      const select = document.createElement("select");
      select.setAttribute("aria-label", `Attach ${displayName(attachment.file)} to a primary PDF`);
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "Assign to primary PDF";
      select.append(blank);
      for (const primary of primaryFiles) {
        const option = document.createElement("option");
        option.value = fileKey(primary);
        option.textContent = displayName(primary);
        select.append(option);
      }
      select.value = assignments.get(attachment.key) || "";
      select.addEventListener("change", () => {
        if (select.value) assignments.set(attachment.key, select.value);
        else assignments.delete(attachment.key);
        renderReview(collectSelection());
      });
      row.append(name, select);
      return row;
    };

    for (const input of [primaryInput, supportingInput, folderInput]) {
      input?.addEventListener("change", refresh);
    }
    refresh();
    return { refresh, getBundles, appendBundlesToFormData, clear };
  }

  function addPrimaryFiles(target, files) {
    for (const file of files) {
      if (isPdf(file)) addFile(target, file);
    }
  }

  function addSupportingFiles(target, files) {
    for (const file of files) {
      if (isSupportedSource(file)) addFile(target, file);
    }
  }

  function addFile(target, file) {
    target.set(fileKey(file), file);
  }

  function fileList(input) {
    return input ? [...input.files] : [];
  }

  function fileKey(file) {
    return `${relativePath(file)}:${file.size}:${file.lastModified}`;
  }

  function relativePath(file) {
    return file.webkitRelativePath || file.name || "source-file";
  }

  function displayName(file) {
    return file.webkitRelativePath || file.name || "Source file";
  }

  function extension(filename) {
    const match = String(filename || "").toLowerCase().match(/\.[^.]+$/);
    return match ? match[0] : "";
  }

  function isPdf(file) {
    return extension(file.name) === ".pdf";
  }

  function isSupportedSource(file) {
    return SUPPORTED_ATTACHMENT_EXTENSIONS.has(extension(file.name));
  }

  function looksSupplementary(filename) {
    return SUPPLEMENTARY_NAME_TEST_PATTERN.test(PathStem(filename));
  }

  function normalizedStudyStem(filename) {
    return PathStem(filename)
      .replace(SUPPLEMENTARY_NAME_PATTERN, " ")
      .replace(/[^a-z0-9]+/gi, " ")
      .trim()
      .replace(/\s+/g, " ")
      .toLowerCase();
  }

  function PathStem(filename) {
    return String(filename || "").replace(/^.*[\\/]/, "").replace(/\.[^.]+$/, "");
  }

  function primaryInputSummary(files) {
    const pdfs = files.filter(isPdf);
    if (!pdfs.length) return "No primary PDFs selected";
    return pdfs.length === 1 ? displayName(pdfs[0]) : `${pdfs.length} primary PDFs selected`;
  }

  function supportingInputSummary(files) {
    const sources = files.filter(isSupportedSource);
    if (!sources.length) return "No supporting files selected";
    return sources.length === 1 ? displayName(sources[0]) : `${sources.length} supporting files selected`;
  }

  function folderInputSummary(files) {
    const sources = files.filter(isSupportedSource);
    if (!sources.length) return "No supported files in folder";
    return `${sources.length} supported files in folder`;
  }

  function plural(count, singular) {
    return count === 1 ? singular : `${singular}s`;
  }

  window.CEREBROStudyBundles = { mountStudyBundlePicker };
})();
