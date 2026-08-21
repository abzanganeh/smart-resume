import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { faqEntries, faqJsonLd } from "@/lib/marketing/faq";

describe("faqEntries", () => {
  it("gives every entry a question and an answer", () => {
    for (const entry of faqEntries(6)) {
      assert.ok(entry.question.trim().length > 0, "question is non-empty");
      assert.ok(entry.answer.trim().length > 0, "answer is non-empty");
    }
  });

  it("asks each question only once", () => {
    const questions = faqEntries(6).map((e) => e.question);
    assert.equal(new Set(questions).size, questions.length);
  });

  it("phrases every question as a question", () => {
    // Generative engines quote Q&A pairs; a heading that is not a question is
    // not a useful FAQ entry.
    for (const entry of faqEntries(6)) {
      assert.match(entry.question, /\?$/);
    }
  });

  it("takes the credit count from the caller rather than hardcoding it", () => {
    // The free-tier grant is API-sourced (GET /api/billing/free-tier). Baking a
    // number into FAQ prose would drift the moment the backend seed changes.
    const six = faqEntries(6).map((e) => e.answer).join(" ");
    const nine = faqEntries(9).map((e) => e.answer).join(" ");
    assert.ok(six.includes("6"), "renders the count it was given");
    assert.ok(nine.includes("9"), "renders a different count when given one");
    assert.notEqual(six, nine);
  });

  it("tells visitors the checkup needs no account", () => {
    // This is the highest-intent fact on the page and the one thing a visitor
    // can act on immediately.
    const text = faqEntries(6)
      .map((e) => `${e.question} ${e.answer}`)
      .join(" ")
      .toLowerCase();
    assert.ok(text.includes("checkup"), "mentions the checkup");
    assert.ok(text.includes("no account"), "states no account is needed");
  });

  it("does not claim anything about model training", () => {
    // The privacy policy makes no training claim, so the marketing page must
    // not invent one. Data questions point at the policy instead.
    const text = faqEntries(6)
      .map((e) => e.answer)
      .join(" ")
      .toLowerCase();
    assert.ok(!text.includes("train"), "no unverifiable training claim");
  });
});

describe("faqJsonLd", () => {
  const entries = [
    { question: "Is it free?", answer: "The checkup is." },
    { question: "Does it fabricate?", answer: "No." },
  ];

  it("emits a schema.org FAQPage", () => {
    const jsonLd = faqJsonLd(entries) as Record<string, unknown>;
    assert.equal(jsonLd["@context"], "https://schema.org");
    assert.equal(jsonLd["@type"], "FAQPage");
  });

  it("emits one Question per entry, each with an accepted Answer", () => {
    const jsonLd = faqJsonLd(entries) as {
      mainEntity: {
        "@type": string;
        name: string;
        acceptedAnswer: { "@type": string; text: string };
      }[];
    };
    assert.equal(jsonLd.mainEntity.length, entries.length);
    jsonLd.mainEntity.forEach((question, index) => {
      assert.equal(question["@type"], "Question");
      assert.equal(question.name, entries[index].question);
      assert.equal(question.acceptedAnswer["@type"], "Answer");
      assert.equal(question.acceptedAnswer.text, entries[index].answer);
    });
  });

  it("survives JSON serialisation, since it is injected into a script tag", () => {
    assert.doesNotThrow(() => JSON.stringify(faqJsonLd(entries)));
  });

  it("rejects an entry with an empty answer instead of emitting invalid markup", () => {
    // Structured data with blank answers is worse than none: it is a spam
    // signal. Fail loudly at build time instead.
    assert.throws(
      () => faqJsonLd([{ question: "Anything?", answer: "  " }]),
      /answer/i,
    );
  });

  it("rejects an entry with an empty question", () => {
    assert.throws(
      () => faqJsonLd([{ question: "  ", answer: "Something." }]),
      /question/i,
    );
  });

  it("produces valid markup for the real FAQ content", () => {
    assert.doesNotThrow(() => faqJsonLd(faqEntries(6)));
  });
});
