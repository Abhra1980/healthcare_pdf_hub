from euriai.langchain import create_chat_model # Import the function to create a chat model - this is a wrapper around Langchain's ChatOpenAI built by EURON

def get_chat_model(api_key: str):

    return create_chat_model(api_key=api_key, 
                             model="gpt-4.1-nano", 
                             temperature=0.7)
    
def ask_chat_model(chat_model, question: str):

    response = chat_model.invoke(question)
    return response.content