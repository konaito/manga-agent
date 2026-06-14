export interface Episode {
  id: string;
  slug: string;
  path: string;
  number: number;
  title: string;
  subtitle: string;
  pageCount: number;
}

export const EPISODES: Episode[] = [
  {
    id: "onibaku-ep01-yobimizu",
    slug: "ep01",
    path: "ep01",
    number: 1,
    title: "第1話",
    subtitle: "呼び水",
    pageCount: 16,
  },
  {
    id: "onibaku-ep02-isourou",
    slug: "ep02",
    path: "ep02",
    number: 2,
    title: "第2話",
    subtitle: "居候",
    pageCount: 16,
  },
];

export function findEpisode(slug: string): Episode | undefined {
  return EPISODES.find((episode) => episode.slug === slug);
}

export function episodeFromLocation(search: string): Episode {
  const slug = new URLSearchParams(search).get("ep") ?? EPISODES[0]!.slug;
  return findEpisode(slug) ?? EPISODES[0]!;
}

export function buildManga(episode: Episode) {
  const pageBase = `/onibaku/${episode.path}/pages`;

  return {
    id: episode.id,
    title: `鬼畜 ${episode.title}「${episode.subtitle}」`,
    author: "konaito",
    pages: Array.from({ length: episode.pageCount }, (_, index) => {
      const pageNumber = String(index + 1).padStart(2, "0");

      return {
        id: `${episode.slug}-page-${pageNumber}`,
        type: "image" as const,
        src: `${pageBase}/page_${pageNumber}.png`,
      };
    }),
  };
}

export function episodeLabel(episode: Episode): string {
  return `${episode.title}「${episode.subtitle}」`;
}

export function episodePdfHref(episode: Episode): string {
  return `/onibaku/${episode.path}/book.pdf`;
}
