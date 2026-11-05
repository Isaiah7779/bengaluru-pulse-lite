import { fireEvent, render, screen } from "@testing-library/react";
import AskPage from "./pages/AskPage";

function respond(handler) {
  global.fetch = jest.fn(async (url, opts = {}) => {
    const [status, body] = handler(new URL(url).pathname, opts);
    return { ok: status < 400, status, json: async () => body };
  });
}

const ANSWER = {
  answer: "From the Bengaluru Pulse documentation:\n- SHORTCUT — shorter distance and shorter travel time. [1]",
  refused: false,
  citations: [{ n: 1, chunk_id: 7, title: "Routing", source_ref: "docs/ROUTING.md", heading: "Shortcut / longcut classification", measured_on: "2026-10-22" }],
  composer: "extractive",
  disclaimer: "Answers quote project documentation only.",
  latency_ms: 4,
};

test("shows a cited answer and opens its source passage", async () => {
  respond((path, opts) => {
    if (path === "/v1/assistant/ask") {
      expect(JSON.parse(opts.body)).toEqual({ question: "What is a shortcut?" });
      return [200, ANSWER];
    }
    if (path === "/v1/assistant/sources/7") return [200, { text: "SHORTCUT — shorter distance and shorter travel time." }];
    return [404, {}];
  });
  render(<AskPage />);
  fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "What is a shortcut?" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  expect(await screen.findByText(/shorter distance and shorter travel time\. \[1\]/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /\[1\] Routing/ }));
  expect(await screen.findByText("SHORTCUT — shorter distance and shorter travel time.")).toBeInTheDocument();
});

test("shows refusals as plain text and server errors", async () => {
  respond(() => [200, { ...ANSWER, refused: true, refusal_code: "out_of_scope", citations: [],
    answer: "I can only help with Bengaluru Pulse. <b>not html</b>" }]);
  render(<AskPage />);
  fireEvent.click(screen.getByRole("button", { name: "Does weather change the ETA?" }));
  expect(await screen.findByText("I can only help with Bengaluru Pulse. <b>not html</b>")).toBeInTheDocument();

  respond(() => [429, { error: { code: "rate_limited", message: "Too many assistant questions" } }]);
  fireEvent.click(screen.getByRole("button", { name: "What is a shortcut in Pulse?" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Too many assistant questions");
});
