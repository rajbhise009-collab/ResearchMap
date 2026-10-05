import { getLibraries } from "../lib/data";
import NotFoundBody from "./components/NotFoundBody";

export default function NotFound() {
  const libs = getLibraries().libraries.map((l) => ({ slug: l.slug, name: l.name, n_papers: l.n_papers }));
  return <NotFoundBody libraries={libs} />;
}
