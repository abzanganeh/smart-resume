import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  HERO_SCROLL_RELEASE_VH,
  HERO_SCROLL_SEGMENT_VH,
  heroMessageProgressFromTrack,
  heroScrollTrackHeightVh,
} from "@/lib/marketing/scrollPin";

describe("heroScrollTrackHeightVh", () => {
  it("sums segment travel plus release tail for seven messages", () => {
    assert.equal(heroScrollTrackHeightVh(7), 7 * HERO_SCROLL_SEGMENT_VH + HERO_SCROLL_RELEASE_VH);
  });

  it("returns only the release tail when there are no messages", () => {
    assert.equal(heroScrollTrackHeightVh(0), HERO_SCROLL_RELEASE_VH);
  });
});

describe("heroMessageProgressFromTrack", () => {
  const MESSAGE_COUNT = 7;

  it("is zero at the start of the track", () => {
    assert.equal(heroMessageProgressFromTrack(0, MESSAGE_COUNT), 0);
    assert.equal(heroMessageProgressFromTrack(-1, MESSAGE_COUNT), 0);
  });

  it("is one once the message share of the track is consumed", () => {
    const total = heroScrollTrackHeightVh(MESSAGE_COUNT);
    const messageShare = (MESSAGE_COUNT * HERO_SCROLL_SEGMENT_VH) / total;
    assert.equal(heroMessageProgressFromTrack(messageShare, MESSAGE_COUNT), 1);
    assert.equal(heroMessageProgressFromTrack(1, MESSAGE_COUNT), 1);
  });

  it("scales linearly through the message portion of the track", () => {
    const total = heroScrollTrackHeightVh(MESSAGE_COUNT);
    const messageShare = (MESSAGE_COUNT * HERO_SCROLL_SEGMENT_VH) / total;
    const halfway = messageShare / 2;
    assert.equal(heroMessageProgressFromTrack(halfway, MESSAGE_COUNT), 0.5);
  });

  it("returns zero for empty catalogs", () => {
    assert.equal(heroMessageProgressFromTrack(0.5, 0), 0);
  });

  it("returns zero for non-finite track progress", () => {
    assert.equal(heroMessageProgressFromTrack(Number.NaN, MESSAGE_COUNT), 0);
  });
});
