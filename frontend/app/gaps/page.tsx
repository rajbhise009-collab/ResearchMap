import { getGapDocs, getLanguage } from "../../lib/data";
import GapsClient from "./GapsClient";

export default function GapsPage() {
  const gaps = getGapDocs();
  const lang = getLanguage();
  return (
    <>
      <div className="hero" style={{ marginBottom: "2.5rem" }}>
        <h1 style={{ fontSize: "2rem" }}>{lang.ui.all_opportunities}</h1>
        <p className="lede">
          Everything the tool found in this library, strongest first. Each one
          says how sure we are and what would undermine it.
        </p>
      </div>
      <GapsClient gaps={gaps} lang={lang} />
    </>
  );
}
