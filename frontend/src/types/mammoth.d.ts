declare module 'mammoth/mammoth.browser' {
  interface MammothMessage {
    type: string;
    message: string;
  }

  interface MammothResult {
    value: string;
    messages: MammothMessage[];
  }

  interface MammothInput {
    arrayBuffer: ArrayBuffer;
  }

  const mammoth: {
    convertToHtml: (input: MammothInput) => Promise<MammothResult>;
  };

  export default mammoth;
}
