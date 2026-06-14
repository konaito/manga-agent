import { createMangaViewer, type MangaViewerInstance } from "@yui540/comimi";
import {
  buildManga,
  episodeFromLocation,
  episodeLabel,
  episodePdfHref,
  EPISODES,
  type Episode,
} from "./episodes";
import "./styles.css";

const viewerRoot = document.querySelector<HTMLElement>("#viewer");
const episodeSelect = document.querySelector<HTMLSelectElement>("#episode-select");
const titleHeading = document.querySelector<HTMLHeadingElement>("#episode-title");
const pdfLink = document.querySelector<HTMLAnchorElement>("#pdf-link");

if (!viewerRoot || !episodeSelect || !titleHeading || !pdfLink) {
  throw new Error("Preview shell is missing required elements.");
}

let viewer: MangaViewerInstance | null = null;
let activeEpisode = episodeFromLocation(window.location.search);

function updateChrome(episode: Episode) {
  document.title = `鬼畜 ${episodeLabel(episode)} — preview`;
  titleHeading.textContent = `鬼畜 ${episodeLabel(episode)}`;
  pdfLink.href = episodePdfHref(episode);
  episodeSelect.value = episode.slug;

  const url = new URL(window.location.href);
  url.searchParams.set("ep", episode.slug);
  window.history.replaceState({}, "", url);
}

async function loadEpisode(episode: Episode) {
  activeEpisode = episode;
  updateChrome(episode);

  const manga = buildManga(episode);

  if (!viewer) {
    viewer = createMangaViewer(viewerRoot, {
      manga,
      settings: {
        readingDirection: "rtl",
      },
    });
    return;
  }

  await viewer.setManga(manga);
}

episodeSelect.addEventListener("change", () => {
  const episode = EPISODES.find((item) => item.slug === episodeSelect.value);
  if (!episode || episode.slug === activeEpisode.slug) {
    return;
  }

  void loadEpisode(episode);
});

for (const episode of EPISODES) {
  const option = document.createElement("option");
  option.value = episode.slug;
  option.textContent = episodeLabel(episode);
  episodeSelect.appendChild(option);
}

void loadEpisode(activeEpisode);
