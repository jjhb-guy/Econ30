const state = {
  allProjects: [],
  allSources: [],
  filteredProjects: []
};

const formatCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0
});

const formatInteger = new Intl.NumberFormat("en-US");

const elements = {
  lastUpdated: document.getElementById("lastUpdated"),
  searchInput: document.getElementById("searchInput"),
  sectorFilter: document.getElementById("sectorFilter"),
  yearFilter: document.getElementById("yearFilter"),
  minInvestment: document.getElementById("minInvestment"),
  minInvestmentLabel: document.getElementById("minInvestmentLabel"),
  kpiInvestment: document.getElementById("kpiInvestment"),
  kpiJobs: document.getElementById("kpiJobs"),
  kpiProjects: document.getElementById("kpiProjects"),
  projectList: document.getElementById("projectList"),
  sourceList: document.getElementById("sourceList"),
  mapLegend: document.getElementById("mapLegend")
};

async function init() {
  const response = await fetch("./data/stl-progress.json");
  if (!response.ok) {
    throw new Error("Could not load data/stl-progress.json");
  }

  const data = await response.json();
  state.allProjects = data.projects ?? [];
  state.allSources = data.sources ?? [];

  elements.lastUpdated.textContent = `Updated ${data.meta?.lastUpdated ?? "unknown"}`;
  bootstrapFilterOptions(state.allProjects);
  bindEvents();
  applyFilters();
}

function bootstrapFilterOptions(projects) {
  const sectors = [...new Set(projects.map((p) => p.sector).filter(Boolean))].sort();
  const years = [...new Set(projects.map((p) => p.year).filter(Boolean))].sort((a, b) => b - a);

  sectors.forEach((sector) => {
    const option = document.createElement("option");
    option.value = sector;
    option.textContent = sector;
    elements.sectorFilter.appendChild(option);
  });

  years.forEach((year) => {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    elements.yearFilter.appendChild(option);
  });

  const maxInvestment = Math.max(1000000, ...projects.map((p) => p.investmentUsd || 0));
  elements.minInvestment.max = String(maxInvestment);
}

function bindEvents() {
  [
    elements.searchInput,
    elements.sectorFilter,
    elements.yearFilter,
    elements.minInvestment
  ].forEach((element) => element.addEventListener("input", applyFilters));
}

function applyFilters() {
  const searchTerm = elements.searchInput.value.trim().toLowerCase();
  const selectedSector = elements.sectorFilter.value;
  const selectedYear = elements.yearFilter.value;
  const minInvestment = Number(elements.minInvestment.value);

  elements.minInvestmentLabel.textContent = formatCurrency.format(minInvestment);

  state.filteredProjects = state.allProjects.filter((project) => {
    const bySearch =
      !searchTerm ||
      project.name.toLowerCase().includes(searchTerm) ||
      project.location?.name?.toLowerCase().includes(searchTerm);
    const bySector = selectedSector === "all" || project.sector === selectedSector;
    const byYear = selectedYear === "all" || String(project.year) === selectedYear;
    const byInvestment = (project.investmentUsd || 0) >= minInvestment;
    return bySearch && bySector && byYear && byInvestment;
  });

  renderKpis(state.filteredProjects);
  renderProjects(state.filteredProjects);
  renderSources(state.filteredProjects, state.allSources);
  renderMapLegend(state.filteredProjects);
}

function renderKpis(projects) {
  const totalInvestment = projects.reduce((sum, project) => sum + (project.investmentUsd || 0), 0);
  const totalJobs = projects.reduce((sum, project) => sum + (project.jobs || 0), 0);

  elements.kpiInvestment.textContent = formatCurrency.format(totalInvestment);
  elements.kpiJobs.textContent = formatInteger.format(totalJobs);
  elements.kpiProjects.textContent = formatInteger.format(projects.length);
}

function renderProjects(projects) {
  elements.projectList.innerHTML = "";

  if (projects.length === 0) {
    elements.projectList.innerHTML = `<li class="empty">No projects match current filters.</li>`;
    return;
  }

  projects.forEach((project) => {
    const item = document.createElement("li");
    item.className = "project-item";
    item.innerHTML = `
      <strong>${project.name}</strong>
      <span class="meta">${project.sector} • ${project.year}</span>
      <span class="meta">${project.location?.name || "Unknown location"}</span>
      <span class="meta">${formatCurrency.format(project.investmentUsd || 0)} • ${formatInteger.format(project.jobs || 0)} jobs</span>
    `;
    elements.projectList.appendChild(item);
  });
}

function renderSources(projects, allSources) {
  elements.sourceList.innerHTML = "";

  const sourceIds = [...new Set(projects.map((project) => project.sourceId))];
  const sources = allSources.filter((source) => sourceIds.includes(source.id));

  if (sources.length === 0) {
    elements.sourceList.innerHTML = `<li class="empty">No source records for current filters.</li>`;
    return;
  }

  sources.forEach((source) => {
    const item = document.createElement("li");
    item.className = "source-item";
    item.innerHTML = `
      <strong>${source.title}</strong>
      <span class="meta">${source.publisher || "Unknown publisher"}</span>
      <span class="meta">${source.publishedDate || "Unknown date"}</span>
      <span class="meta">${source.path}</span>
    `;
    elements.sourceList.appendChild(item);
  });
}

function renderMapLegend(projects) {
  elements.mapLegend.innerHTML = "";

  projects.forEach((project) => {
    const item = document.createElement("li");
    item.className = "meta";
    item.textContent = `${project.location?.name || "Unknown"}: ${project.name}`;
    elements.mapLegend.appendChild(item);
  });
}

init().catch((error) => {
  elements.projectList.innerHTML = `<li class="empty">Failed to load dashboard data: ${error.message}</li>`;
});
