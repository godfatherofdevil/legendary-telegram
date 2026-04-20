const { deserialize, serialize } = require("v8");

if (typeof globalThis.structuredClone !== "function") {
  globalThis.structuredClone = (value, options = {}) => {
    if (options.transfer?.length) {
      throw new Error(
        "Transfer lists are not supported by the local structuredClone fallback.",
      );
    }

    return deserialize(serialize(value));
  };
}
