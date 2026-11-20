/** The explained passage to bring into view, once per `nonce`: the editor selects it and the PDF scrolls to it. */
export interface PassageFocus {
  passage: string;
  nonce: number;
}
