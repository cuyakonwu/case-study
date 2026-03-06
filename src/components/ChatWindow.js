import React, { useState, useEffect, useRef } from "react";
import "./ChatWindow.css";
import { getAIMessage } from "../api/api";
import { marked } from "marked";

function ChatWindow() {

  const defaultMessage = [{
    role: "assistant",
    content: "Hi! I'm your PartSelect assistant. Are you looking for a specific Refrigerator or Dishwasher part, or do you need help troubleshooting an issue?"
  }];

  const [messages, setMessages] = useState(defaultMessage)
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async (input) => {
    if (input.trim() !== "") {
      // Set user message
      setMessages(prevMessages => [...prevMessages, { role: "user", content: input }]);
      setInput("");

      // Call API & set assistant message
      setIsLoading(true);
      const newMessage = await getAIMessage(input);
      setMessages(prevMessages => [...prevMessages, newMessage]);
      setIsLoading(false);
    }
  };

  return (
    <div className="messages-container">
      {messages.map((message, index) => (
        <div key={index} className={`${message.role}-message-container`}>
          {message.content && (
            <div className={`message ${message.role}-message`}>
              <div dangerouslySetInnerHTML={{ __html: marked(message.content).replace(/<p>|<\/p>/g, "") }}></div>
              {message.suggested_parts && message.suggested_parts.length > 0 && (
                <div className="suggested-parts-container">
                  <p className="suggested-parts-title">Recommended Parts:</p>
                  {message.suggested_parts.map((part, pIndex) => (
                    <a key={pIndex} href={part.url} target="_blank" rel="noopener noreferrer" className="part-card">
                      <div className="part-card-title">{part.title}</div>
                      <div className="part-card-number">Part No: {part.part_number}</div>
                      <div className="part-card-desc">{part.description.substring(0, 100)}...</div>
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ))}

      {isLoading && (
        <div className="assistant-message-container">
          <div className="message assistant-message typing-indicator">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
      <div className="input-area">
        <div className="input-area-inner">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a message..."
            onKeyPress={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                handleSend(input);
                e.preventDefault();
              }
            }}
          />
          <button className="send-button" onClick={() => handleSend(input)}>
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatWindow;
