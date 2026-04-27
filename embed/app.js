const DATA_URL = "../data/totals.json";

const totalRaisedEl = document.getElementById("total-raised");
const totalTargetEl = document.getElementById("total-target");
const totalPercentEl = document.getElementById("total-percent");
const totalProgressEl = document.getElementById("total-progress");
const lastUpdatedEl = document.getElementById("last-updated");
const warningEl = document.getElementById("warning");
const campaignListEl = document.getElementById("campaign-list");
const campaignTemplate = document.getElementById("campaign-template");

function formatCurrency(amount) {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: 0
  }).format(Number(amount || 0));
}

function formatPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

function setProgress(el, percent) {
  const bounded = Math.max(0, Math.min(100, Number(percent || 0)));
  el.style.width = `${bounded}%`;
}

function formatTimestamp(value) {
  if (!value) return "Last updated: never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Last updated: unknown";
  return `Last updated: ${date.toLocaleString()}`;
}

function renderCampaigns(campaigns) {
  campaignListEl.innerHTML = "";
  campaigns.forEach((campaign) => {
    const node = campaignTemplate.content.cloneNode(true);
    node.querySelector(".campaign-name").textContent = campaign.name;
    const iconEl = node.querySelector(".campaign-icon");
    if (campaign.icon) {
      const img = document.createElement("img");
      img.src = campaign.icon;
      img.alt = campaign.name + " logo";
      iconEl.appendChild(img);
    } else {
      iconEl.remove();
    }
    const link = node.querySelector(".campaign-link");
    link.href = campaign.sourceUrl;
    node.querySelector(".campaign-raised").textContent = formatCurrency(campaign.raised);
    node.querySelector(".campaign-target").textContent = formatCurrency(campaign.target);
    node.querySelector(".campaign-percent").textContent = formatPercent(campaign.progressPercent);
    setProgress(node.querySelector(".progress-fill"), campaign.progressPercent);
    campaignListEl.appendChild(node);
  });
}

async function init() {
  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }

    const payload = await response.json();
    const totals = payload.totals || {};
    const meta = payload.meta || {};
    const campaigns = payload.campaigns || [];

    totalRaisedEl.textContent = formatCurrency(totals.raised);
    totalTargetEl.textContent = formatCurrency(totals.target);
    totalPercentEl.textContent = formatPercent(totals.progressPercent);
    setProgress(totalProgressEl, totals.progressPercent);
    lastUpdatedEl.textContent = formatTimestamp(meta.generatedAt);
    renderCampaigns(campaigns);

  } catch (error) {
    lastUpdatedEl.textContent = "Could not load totals data.";
    warningEl.classList.remove("hidden");
    warningEl.textContent = "Data is temporarily unavailable. Please refresh shortly.";
    console.error(error);
  }
}

init();
