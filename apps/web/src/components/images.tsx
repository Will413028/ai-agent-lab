import type { ImageSearchResult } from "../lib/images.generated";

export function ImageResults({ result }: { result: ImageSearchResult }) {
  return <section className="panel"><h2>圖片來源 · {result.provider}</h2>
    {result.images.length === 0 ? <p>沒有找到符合條件的圖片。</p> : <div className="image-grid">{result.images.map((image, index) => <figure key={`${image.url}-${index}`}>
      {/* Commons returns varying external thumbnail sizes; native lazy images preserve attribution. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={image.url} alt={image.title} loading="lazy" referrerPolicy="no-referrer" />
      <figcaption><a href={image.source_url} target="_blank" rel="noreferrer">{image.title}</a><p>{image.artist}</p><a href={image.license_url} target="_blank" rel="noreferrer">{image.license}</a></figcaption>
    </figure>)}</div>}
  </section>;
}
